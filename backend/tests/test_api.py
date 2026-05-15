import unittest
import json
import sys
import os

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

# Set testing flag BEFORE importing app to prevent background minikube calls
os.environ['TESTING'] = 'true'
from app import app

class BackendTestCase(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        self.app = app.test_client()

    def test_health_check(self):
        """Test the root endpoint returns a 200 status."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)

    @patch('app.users_col')
    def test_invalid_login(self, mock_users_col):
        """Test login with non-existent user."""
        mock_users_col.find_one.return_value = None
        response = self.app.post('/login',
                                 data=json.dumps({"username": "nonexistent", "password": "123"}),
                                 content_type='application/json')
        data = json.loads(response.data)
        self.assertEqual(data['status'], False)
        # Check for 'error' key which is what app.py actually uses
        self.assertIn("error", data)

    def test_signup_validation(self):
        """Test signup requires both username and password (should not crash)."""
        response = self.app.post('/signup',
                                 data=json.dumps({"username": "onlyuser"}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400) # Should return 400 Bad Request
        data = json.loads(response.data)
        self.assertEqual(data['status'], False)
        self.assertIn("required", data['error'].lower())

if __name__ == '__main__':
    unittest.main()
