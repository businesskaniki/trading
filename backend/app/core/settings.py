from backend.app.core.config import settings


class AppSettings:

    APP_NAME = settings.APP_NAME

    VERSION = settings.APP_VERSION

    DEBUG = settings.DEBUG

    API_PREFIX = settings.API_PREFIX

    DATABASE_URL = settings.DATABASE_URL

    REDIS_URL = settings.REDIS_URL


app_settings = AppSettings()
