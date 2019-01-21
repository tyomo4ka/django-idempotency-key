from functools import wraps
from typing import Tuple

from django.core.cache import cache
from django.test import modify_settings, override_settings
from rest_framework import status

from idempotency_key.encoders import IdempotencyKeyEncoder
from idempotency_key.storage import IdempotencyKeyStorage
from tests.tests.utils import for_all_methods


def set_middleware(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with modify_settings(MIDDLEWARE={
            'append': ['idempotency_key.middleware.IdempotencyKeyMiddleware'],
            'remove': ['idempotency_key.middleware.ExemptIdempotencyKeyMiddleware'],
        }):
            return func(*args, **kwargs)

    return wrapper


class MyEncoder(IdempotencyKeyEncoder):
    def encode_key(self, request, key):
        return '0000000000000000000000000000000000000000000000000000000000000000'


class MyStorage(IdempotencyKeyStorage):

    def __init__(self):
        self.idempotency_key_cache_data = dict()

    def store_data(self, encoded_key: str, response: object) -> None:
        pass

    def retrieve_data(self, encoded_key: str) -> Tuple[bool, object]:
        return False, None


@for_all_methods(set_middleware)
class TestMiddlewareInclusive:
    the_key = '7495e32b-709b-4fae-bfd4-2497094bf3fd'
    urls = {
        name: '/views/{}/'.format(name) for name in
        ['get-voucher', 'create-voucher', 'create-voucher-exempt', 'create-voucher-no-decorators',
         'create-voucher-manual', 'create-voucher-exempt-test-1', 'create-voucher-exempt-test-2']
    }

    def test_get_exempt(self, client):
        """Basic GET method is exempt by default because it is a read-only function"""
        response = client.get(self.urls['get-voucher'], secure=True)
        assert response.status_code == status.HTTP_200_OK
        request = response.wsgi_request
        assert request.idempotency_key_exempt is True
        assert request.idempotency_key_manual is False

    def test_post_exempt(self, client):
        """Test a POST method that has been marked as exempt"""
        response = client.post(self.urls['create-voucher-exempt'], data={}, secure=True)
        assert response.status_code == status.HTTP_201_CREATED
        request = response.wsgi_request
        assert request.idempotency_key_exempt is True
        assert request.idempotency_key_manual is False

        response = client.post(self.urls['create-voucher-exempt'], data={}, secure=True)
        assert response.status_code == status.HTTP_201_CREATED
        request = response.wsgi_request
        assert request.idempotency_key_exempt is True
        assert request.idempotency_key_manual is False

    def test_post_no_decorators(self, client):
        response = client.post(self.urls['create-voucher-no-decorators'], data={}, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response.status_code == status.HTTP_201_CREATED
        request = response.wsgi_request
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False

        response = client.post(self.urls['create-voucher-no-decorators'], data={}, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response.status_code == status.HTTP_409_CONFLICT
        request = response.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == '4d500807b9fcd9f19b7d0d60878f92564eae80e9bff8b18e1a4257080c3d5325'

    def test_bad_request_no_key_specified(self, client):
        """
        POSTing to a view function that requires an idempotency key which is not specified in the header will cause a
        400 BAD REQUEST to be generated.
        """
        response = client.post(self.urls['create-voucher'], secure=True)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        request = response.wsgi_request
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False

    @override_settings(
        IDEMPOTENCY_KEY={}
    )
    def test_middleware_duplicate_request(self, client):
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_409_CONFLICT
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == 'b204f77b6555b66c71296426364f22f65ffde694152e1e5b17f8f024b33e2df3'

    @override_settings(
        IDEMPOTENCY_KEY={'CONFLICT_STATUS_CODE': None}
    )
    def test_middleware_duplicate_request_use_original_status_code(self, client):
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_201_CREATED
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == 'b204f77b6555b66c71296426364f22f65ffde694152e1e5b17f8f024b33e2df3'

    @override_settings(
        IDEMPOTENCY_KEY={'CONFLICT_STATUS_CODE': status.HTTP_200_OK}
    )
    def test_middleware_duplicate_request_use_different_status_code(self, client):
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_200_OK
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == 'b204f77b6555b66c71296426364f22f65ffde694152e1e5b17f8f024b33e2df3'

    def test_middleware_duplicate_request_manual_override(self, client):
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher-manual'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher-manual'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)

        # The view code forces a 200 OK to be returned if this is a repeated request.
        assert response2.status_code == status.HTTP_200_OK
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is True
        assert request.idempotency_key_encoded_key == '96cbe9a5f3e24c87f6cc8808b6cd2d91ecd2bf9b8e52fa4b34ad6b3d5626dabb'

    @override_settings(
        IDEMPOTENCY_KEY={
            'ENCODER_CLASS': 'tests.tests.test_middleware.MyEncoder'
        }
    )
    def test_middleware_custom_encoder(self, client):
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_409_CONFLICT
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == '0000000000000000000000000000000000000000000000000000000000000000'

    @override_settings(
        IDEMPOTENCY_KEY={
            'STORAGE_CLASS': 'tests.tests.test_middleware.MyStorage'
        }
    )
    def test_middleware_custom_storage(self, client):
        """
        In this test to prove the new custom storage class is being used by creating one that does not to store any
        information. Therefore a 409 conflict should never occur and the key will never exist.
        """
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_201_CREATED
        request = response2.wsgi_request
        assert request.idempotency_key_exists is False
        assert request.idempotency_key_response is None
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == 'b204f77b6555b66c71296426364f22f65ffde694152e1e5b17f8f024b33e2df3'

    def test_idempotency_key_decorator(self, client):
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_409_CONFLICT
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_manual is False
        assert request.idempotency_key_encoded_key == 'b204f77b6555b66c71296426364f22f65ffde694152e1e5b17f8f024b33e2df3'

    def test_idempotency_key_exempt_1(self, client):
        response = client.post(self.urls['create-voucher-exempt-test-1'], {}, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code
        request = response.wsgi_request
        assert request.idempotency_key_exempt is True

    def test_idempotency_key_exempt_2(self, client):
        response = client.post(self.urls['create-voucher-exempt-test-2'], {}, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert status.HTTP_201_CREATED == response.status_code
        request = response.wsgi_request
        assert request.idempotency_key_exempt is True

    @override_settings(
        IDEMPOTENCY_KEY={
            'STORAGE_CLASS': 'idempotency_key.storage.CacheKeyStorage'
        }
    )
    def test_middleware_cache_storage(self, client, settings):
        """
        Test Django cache storage
        """
        cache.clear()
        voucher_data = {
            'id': 1,
            'name': 'myvoucher0',
            'internal_name': 'myvoucher0',
        }

        response = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                               HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response.status_code == status.HTTP_201_CREATED

        response2 = client.post(self.urls['create-voucher'], voucher_data, secure=True,
                                HTTP_IDEMPOTENCY_KEY=self.the_key)
        assert response2.status_code == status.HTTP_409_CONFLICT
        request = response2.wsgi_request
        assert request.idempotency_key_exists is True
        assert request.idempotency_key_response == response2
        assert request.idempotency_key_exempt is False
        assert request.idempotency_key_encoded_key == 'b204f77b6555b66c71296426364f22f65ffde694152e1e5b17f8f024b33e2df3'
