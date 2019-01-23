from django.conf import settings
from django.utils import module_loading

from idempotency_key import status


def idempotency_key_exists(request):
    return getattr(request, 'idempotency_key_exists', False)


def idempotency_key_response(request):
    return getattr(request, 'idempotency_key_response', None)


def get_storage_class():
    idkey_settings = getattr(settings, 'IDEMPOTENCY_KEY', dict())
    return module_loading.import_string(idkey_settings.get('STORAGE_CLASS', 'idempotency_key.storage.MemoryKeyStorage'))


def get_encoder_class():
    idkey_settings = getattr(settings, 'IDEMPOTENCY_KEY', dict())
    return module_loading.import_string(idkey_settings.get('ENCODER_CLASS', 'idempotency_key.encoders.BasicKeyEncoder'))


def get_conflict_code():
    idkey_settings = getattr(settings, 'IDEMPOTENCY_KEY', dict())
    return idkey_settings.get('CONFLICT_STATUS_CODE', status.HTTP_409_CONFLICT)


def get_cache_name():
    idkey_settings = getattr(settings, 'IDEMPOTENCY_KEY', dict())
    return idkey_settings.get('CACHE_NAME', 'default')
