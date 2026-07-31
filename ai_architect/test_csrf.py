import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_architect.settings')
import django
django.setup()

from django.test import Client
from django.urls import reverse

client = Client()
response = client.get('/signup/')
print('Status code:', response.status_code)
print('Cookies:', client.cookies)
# Get the token from the context
# We can parse the content, but let's use the context if available?
# Actually, the response.context is available only if the response is a TemplateResponse.
# For simplicity, let's extract the token from the HTML.
import re
html = response.content.decode('utf-8')
match = re.search(r'name=\"csrfmiddlewaretoken\" value=\"([^\"]+)\"', html)
if match:
    token = match.group(1)
    print('Token from form:', token)
else:
    print('Token not found')
    # Print a snippet
    print(html[:500])
    
# Also, let's see what the cookie is
csrf_cookie = client.cookies.get('csrftoken')
if csrf_cookie:
    print('CSRF cookie:', csrf_cookie.value)
else:
    print('No csrftoken cookie')
    
# Now try to post
data = {
    'name': 'Test User',
    'email': 'test2@example.com',
    'password': 'password123',
    'terms': 'on',
    'csrfmiddlewaretoken': token,
}
post_response = client.post('/signup/', data)
print('POST status:', post_response.status_code)
print('POST cookies:', post_response.cookies)
if post_response.status_code == 302:
    print('Redirect to:', post_response.url)
else:
    print('Response content (first 500 bytes):', post_response.content[:500])
