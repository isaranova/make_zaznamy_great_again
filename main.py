import datetime
import json
import pickle
from datetime import date
from os import path

import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.select import Select

import config


def save_to_pkl(obj, name):
    with open(name + '.pkl', 'wb') as file:
        pickle.dump(obj, file, pickle.HIGHEST_PROTOCOL)


def get_from_pkl(name):
    try:
        with open(name + '.pkl', 'rb') as file:
            return pickle.load(file)
    except FileNotFoundError:
        return None


def send_post_request_to_notifier(data):
    url = config.NOTIFIER_SERVER
    json_string = json.dumps(data, ensure_ascii=False).encode('UTF-8')
    x = requests.post(url, data=json_string, headers=config.SECURITY_HEADER)

    print(f'Server response: {x.status_code}: {x.text}')


class ZaznamyScraper:
    def __init__(self, reload_subjects=False):
        """
        Initializes Selenium Firefox browsers including login, loads saved subjects that have
        recording allowed and loads contacts data to avoid unnecessary contact scraping.

        :param reload_subjects: True to ignore saved subjects and reload them.
        """
        self.user = config.USER
        self.password = config.PASSWORD
        self.browser = self.init_driver()
        self.contact_browser = self.init_driver()
        self.login()

        allowed_subjects = get_from_pkl(config.ALLOWED_SUBJECTS_FILE)
        if allowed_subjects and not reload_subjects:
            self.allowed_subjects = allowed_subjects
        else:
            allowed_subjects = self.get_all_subjects_info()
            save_to_pkl(allowed_subjects, config.ALLOWED_SUBJECTS_FILE)

        self.contact_infos = get_from_pkl(config.CONTACT_INFO_FILE)
        if not self.contact_infos:
            save_to_pkl(dict(), config.CONTACT_INFO_FILE)
            self.contact_infos = dict()

    def __del__(self):
        self.browser.quit()
        self.contact_browser.quit()

    def init_driver(self):
        """
        Drivers are initialized in headless mode.
        :return: Initialized Firefox driver.
        """
        options = Options()
        options.headless = True
        driver = webdriver.Firefox(options=options, executable_path=path.abspath(config.GECKODRIVER_PATH))
        return driver

    def login(self):
        """
        Login to CAS account with config provided username and password.
        """
        self.browser.get(config.CAS_URL)
        self.browser.find_element(By.ID, 'login').send_keys(self.user)
        self.browser.find_element(By.ID, 'password').send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, 'input[name="doLogin"]').click()

        try:
            self.check_access_to_zaznamy()
        except Exception as ex:
            raise Exception(f'Could not access video server: {ex}')

    def check_access_to_zaznamy(self):
        self.browser.get(config.ZAZNAMY_URL)
        try:
            self.browser.find_element(By.ID, 'password')
        except NoSuchElementException:
            pass
        else:
            raise Exception('No access to zaznamy.')

    def get_all_subjects_info(self):
        """
        Gets all subjects from the video server, their IDs and permission to record.

        :return: Dictionary of subjects with their name, ID and permission.
        """
        subjects = dict()

        self.browser.get(config.ALLOWED_ZAZNAMY_URL)
        options = [
            [option.text, option.get_attribute('value')]
            for option in Select(self.browser.find_element(By.CSS_SELECTOR, 'select')).options
        ]

        for subject, subject_id in options:
            selectbox = Select(self.browser.find_element(By.CSS_SELECTOR, 'select'))
            submit_btn = self.browser.find_element(By.CSS_SELECTOR, 'input[value="Zvolit"]')
            subject_abr = subject.split()[0]  # should be first
            selectbox.select_by_value(subject_id)
            submit_btn.click()

            subjects[subject_abr] = {
                'nazev': subject,
                'id': subject_id,
                'zaznam_povolen': False
            }
            if 'záznam: povolen' in self.browser.find_element(By.CSS_SELECTOR, 'td[width="100%"]').text:
                subjects[subject_abr]['zaznam_povolen'] = True

        return subjects

    def get_notification_data(self, year=date.today().year):
        """
        Gets all data needed for notifications. Goes through a list of recordings that have been published in current
        year and fetches those that were not published for students. These recording are listed for every owner with
        owners contact email. Every recording record has it's datetime in ISO format, subject name and abbreviation,
        and the current permission (e.g. 'persons').

        :param year: Year to be searched for recordings.
        :return: Dictionary of owners with their contact info and list of recordings to be published.
        """
        notifications = dict()

        self.browser.get(config.ZAZNAMY_INFO_URL.format(year=year))
        table = self.browser.find_element(By.CSS_SELECTOR, 'table:nth-child(1) table:nth-child(6)')
        rows = table.find_elements(By.CSS_SELECTOR, 'tr[valign="top"')
        for row in rows:
            date_time, subject_name, permissions, zaznam_owner = row.find_elements(By.CSS_SELECTOR, 'td')
            if permissions.text in config.NOT_PUBLISHED_ZAZNAM_PERM:
                subject_abr = subject_name.text.split()[0]

                if zaznam_owner.text in notifications:
                    notifications[zaznam_owner.text]['seznam_nepublikovanych_zaznamu'].append(
                        {
                            'datum_zaznamu': self.get_expected_date_time_format(date_time.text),
                            'nazev_predmetu': subject_name.text,
                            'zkratka_predmetu': subject_abr,
                            'aktualni_povoleni': permissions.text
                        }
                    )
                else:
                    notifications[zaznam_owner.text] = {
                        'seznam_nepublikovanych_zaznamu': [
                            {
                                'datum_zaznamu': self.get_expected_date_time_format(date_time.text),
                                'nazev_predmetu': subject_name.text,
                                'zkratka_predmetu': subject_abr,
                                'aktualni_povoleni': permissions.text
                            }
                        ],
                        'owner_contact': self.get_zaznam_owner_contact(
                            owner_name=zaznam_owner.text,
                            subject_id=self.allowed_subjects[subject_abr]['id']
                        ),
                    }

        save_to_pkl(self.contact_infos, config.CONTACT_INFO_FILE)
        return notifications

    @staticmethod
    def get_expected_date_time_format(datum):
        datetime_datum = datetime.datetime.strptime(datum, '%d. %m. %Y, %H:%M')
        return datetime_datum.strftime('%Y-%m-%dT%H:%M:%SZ')

    def get_zaznam_owner_contact(self, owner_name, subject_id):
        """
        Gets owner's contact email from subject's card. Looks for the link to owner's card and fetches the
        email from there. Handles non-FIT employees and cases when the owner is not listed on the subject's card.
        For example in case the owner was just helping out in the subject (Katka Zmolikova).

        :param owner_name: String name of the owner. Expected full name with titles.
        :param subject_id: String ID of the subject.
        :return: String email of the owner.
        """
        if owner_name in self.contact_infos:
            return self.contact_infos[owner_name]

        self.contact_browser.get(config.SUBJECT_CARD_URL.format(subject_id=subject_id))
        try:
            link_el = self.contact_browser.find_element(By.XPATH, f'//a[text() = "{owner_name}"]')
            link = link_el.get_attribute('href')
        except NoSuchElementException:
            # not on ISS subject card :(
            if owner_name == 'Žmolíková Kateřina, Ing.':
                return 'izmolikova@fit.vut.cz'
            # empty email better than no email
            return ''

        self.contact_browser.get(link)
        try:
            email = self.contact_browser.find_element(
                By.XPATH, '//th[text()="E-mail"]/following-sibling::td/a'
            ).text
        except NoSuchElementException:
            # if not FIT employee
            try:
                email = self.contact_browser.find_element(
                    By.CSS_SELECTOR, '.b-profile__contact span:nth-of-type(2)'
                ).text
            except NoSuchElementException:
                email = self.contact_browser.find_element(
                    By.CSS_SELECTOR, '.b-profile__contact span'
                ).text

        self.contact_infos[owner_name] = email
        return email

    @staticmethod
    def convert_to_expected_format(notifications):
        """
        For better deserialization, we need to have list as the top structure.

        :param notifications: Notifications dict from the get_notification_data method.
        :return: Expected data structure for communication with Notifier server.
        """
        exp_form = []
        for owner_name, values in notifications.items():
            convert = {
                'owner_name': owner_name,
                **values
            }
            exp_form.append(convert)

        return exp_form


if __name__ == '__main__':
    # CONTACTS OUTPUT
    contacts = get_from_pkl(config.CONTACT_INFO_FILE)
    with open('contacts_out', 'w', encoding='utf8') as json_file:
        json.dump(contacts, json_file, ensure_ascii=False, indent=2)

    # NOTIFICATIONS MAIN
    try:
        zscrp = ZaznamyScraper()
        data = zscrp.get_notification_data()
        formatted_data = zscrp.convert_to_expected_format(data)

        with open(config.OUTPUT_FILE, 'w', encoding='utf8') as json_file:
            json.dump(formatted_data, json_file, ensure_ascii=False, indent=2)

        send_post_request_to_notifier(formatted_data)
    except Exception as ex:
        raise Exception(f'Scraper could not finish properly: {ex}')
