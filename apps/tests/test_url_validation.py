import pytest
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
import validators

invalid_path_list = [
    "invalid space",
    'invalid_"_double_quote',
    "invalid_<_less_than_sign",
    "invalid_\\_backslash",
    "invalid_|_pipe",
    "invalid_^_caret",
    "invalid_{_left_curly_brace",
    "invalid_?_question_mark",
    ]

valid_path_list = [
    "valid_%20_space",
    "valid_%22_double_quote",
    "valid_%3C_less_than_sign",
    "valid_%5C_backslash",
    "valid_%7C_pipe",
    "valid_%5E_caret",
    "valid_%7B_left_curly_brace",
    "valid_%3F_question_mark"
]

@pytest.mark.parametrize(
    "custom_default_url",
    invalid_path_list,
)
def test_fail_validation_custom_default_url_using_django_url_validator(custom_default_url):
    
    valid_url = "https://cool-subdomaina.studio.130.229.147.133.nip.io"
    
    url = valid_url + "/" + custom_default_url
    
    print(url)

    result = True

    try:
        URLValidator()(url)
        
    except ValidationError:
        result = False
        
    assert not result
    
@pytest.mark.parametrize(
    "custom_default_url",
    valid_path_list,
)
def test_pass_validation_custom_default_url_using_django_url_validator(custom_default_url):
    
    valid_url = "https://cool-subdomaina.studio.130.229.147.133.nip.io"
    
    url = valid_url + "/" + custom_default_url
    
    print(url)

    result = True

    try:
        URLValidator()(url)
        
    except ValidationError:
        result = False
        
    assert result

@pytest.mark.parametrize(
    "custom_default_url",
    invalid_path_list,
)
def test_fail_validation_custom_default_url_using_python_validators_package(custom_default_url):
    
    valid_url = "https://cool-subdomaina.studio.130.229.147.133.nip.io"
    
    url = valid_url + "/" + custom_default_url
    
    print(url)

    result = validators.url(url)
        
    assert not result
    
@pytest.mark.parametrize(
    "custom_default_url",
    valid_path_list,
)
def test_pass_validation_custom_default_url_using_python_validators_package(custom_default_url):
    
    valid_url = "https://cool-subdomaina.studio.130.229.147.133.nip.io"
    
    url = valid_url + "/" + custom_default_url
    
    print(url)

    result = validators.url(url)
        
    assert result