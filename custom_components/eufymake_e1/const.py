"""Constants for the eufyMake E1 integration."""

DOMAIN = "eufymake_e1"

CONF_APP_DOMAIN = "app_domain"
CONF_AUTH_TOKEN = "auth_token"
CONF_CA_FILE = "ca_file"
CONF_CACHE_DIR = "cache_dir"
CONF_COUNTRY = "country"
CONF_REGION = "region"
CONF_DEVICE_SN = "device_sn"
CONF_EMAIL = "email"
CONF_FIRMWARE_VERSION = "firmware_version"
CONF_MAKE_IT_REAL_DOMAIN = "make_it_real_domain"
CONF_MQTT_HOST = "mqtt_host"
CONF_PASSWORD = "password"
CONF_SECRET_KEY = "secret_key"
CONF_SETUP_EXPORT = "setup_export"
CONF_USER_ID = "user_id"

REGION_US = "us"
REGION_EU = "eu"
REGION_OPTIONS = [REGION_US, REGION_EU]
US_REGION_COUNTRIES = {"AR", "AU", "BR", "BS", "CA", "CU", "MX", "NZ", "US"}

DEFAULT_APP_DOMAIN = "make-app-eu.ankermake.com"
DEFAULT_MAKE_IT_REAL_DOMAIN = "aiot-api-eu.ankermake.com"
DEFAULT_MQTT_HOST = "make-mqtt-eu.ankermake.com"
