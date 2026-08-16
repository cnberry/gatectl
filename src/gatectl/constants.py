"""MyQ residential client constants.

The endpoint and application metadata are undocumented and can change without
notice. They were validated against the August 2026 community implementation
at https://github.com/bvdcode/myq-home-assistant (MIT, Vadim Belov).
"""

from datetime import timedelta

IDENTITY_BASE_URL = "https://partner-identity.myq-cloud.com"
ACCOUNTS_BASE_URL = "https://accounts.myq-cloud.com"
DEVICES_BASE_URL = "https://devices.myq-cloud.com"
GARAGE_DEVICES_BASE_URL = "https://account-devices-gdo.myq-cloud.com"

OAUTH_CLIENT_ID = "ANDROID_CGI_MYQ"
OAUTH_REDIRECT_URI = "com.myqops://android"
OAUTH_SCOPE = "MyQ_Residential offline_access"
APP_VERSION = "5.243.1.73243"
USER_AGENT = "sdk_gphone_x86/Android 11"
BRAND_ID = "1"

FIREBASE_PROJECT_ID = "myq-transition-test"
FIREBASE_APP_ID = "1:169499880894:android:120796f2b5e44ca7"
FIREBASE_API_KEY = "AIzaSyDYwdJBRp6H3UhrCp5LGY8XTPJG7hTeCgw"
FIREBASE_DEBUG_TOKEN = "25A02BB5-4064-4555-9414-F3449D5E5E75"
ANDROID_PACKAGE = "com.chamberlain.android.liftmaster.myq"
ANDROID_CERT_SHA1 = "da2bda70ee8a9062d076babe65924caf9a8b98e9"

MFA_METHOD_EMAIL = "email"
MFA_METHOD_SMS = "sms"
TOKEN_EXPIRY_MARGIN = timedelta(minutes=1)
