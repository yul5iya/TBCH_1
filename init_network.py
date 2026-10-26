import requests

requests.post('http://localhost:5001/nodes/register', json={'nodes': ['http://localhost:5002', 'http://localhost:5003']})
requests.post('http://localhost:5002/nodes/register', json={'nodes': ['http://localhost:5001', 'http://localhost:5003']})
requests.post('http://localhost:5003/nodes/register', json={'nodes': ['http://localhost:5001', 'http://localhost:5002']})
