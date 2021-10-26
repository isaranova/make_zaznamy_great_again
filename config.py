USER = ''
# CAS username
PASSWORD = ''
# CAS password
GECKODRIVER_PATH = ''
# geckodriver path

CAS_URL = 'https://cas.fit.vutbr.cz/'
ZAZNAMY_URL = 'https://video1.fit.vutbr.cz/av/'
ALLOWED_ZAZNAMY_URL = 'https://video1.fit.vutbr.cz/av/no_streaming.php'
ZAZNAMY_INFO_URL = 'https://video1.fit.vutbr.cz/av/records-list.php?datum={year}&nazev=___&SubmitButton=Vyhledat'

ALLOWED_SUBJECTS_FILE = 'allowed_subjects'
NOT_PUBLISHED_ZAZNAM_PERM = ['persons', 'lects', 'dep', 'emps']

CONTACT_INFO_FILE = 'contact_info'
SUBJECT_CARD_URL = 'https://www.fit.vut.cz/study/course/{subject_id}/'

NOTIFICATIONS_FILE = 'notifications'
OUTPUT_FILE = 'notifications_out'

SECURITY_HEADER = {}
# for access to notifier server
NOTIFIER_SERVER = 'https://func-recording-notifier.azurewebsites.net/api/notify'
