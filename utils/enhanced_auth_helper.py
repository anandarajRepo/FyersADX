"""
Enhanced Authentication Helper for Fyers API - WITH TOKEN REFRESH.

Implements automatic token refresh matching FyersORB implementation.
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from urllib.parse import parse_qs, urlparse
import json
import requests

try:
    from fyers_apiv3 import fyersModel
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False
    logging.warning("Fyers API not available")

from config.settings import FyersConfig

logger = logging.getLogger(__name__)


class FyersAuthenticationHelper:
    """
    Authentication helper for Fyers API - matches FyersORB implementation.

    Features:
    - OAuth 2.0 flow
    - Secure token storage in .env
    - Simple token validation (exists or not)
    - PIN-based authentication
    """

    def __init__(self, config: FyersConfig):
        """
        Initialize authentication helper.

        Args:
            config: FyersConfig object
        """
        self.config = config
        self.session = None
        self.auto_open_browser = False

        self.client_id = os.environ.get('FYERS_CLIENT_ID')
        self.secret_key = os.environ.get('FYERS_SECRET_KEY')
        self.redirect_uri = os.environ.get('FYERS_REDIRECT_URI', "https://trade.fyers.in/api-login/redirect-to-app")
        self.refresh_token = os.environ.get('FYERS_REFRESH_TOKEN')
        self.access_token = os.environ.get('FYERS_ACCESS_TOKEN')
        self.pin = os.environ.get('FYERS_PIN')

        # API endpoints
        self.auth_url = "https://api-t1.fyers.in/api/v3/generate-authcode"
        self.token_url = "https://api-t1.fyers.in/api/v3/validate-authcode"
        self.refresh_url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
        self.profile_url = "https://api-t1.fyers.in/api/v3/profile"

        logger.info("Initialized FyersAuthenticationHelper")

    def authenticate(self) -> bool:
        """
        Perform complete authentication flow.

        Returns:
            bool: True if authentication successful
        """
        if not FYERS_AVAILABLE:
            logger.error("Fyers API not available - install with: pip install fyers-apiv3")
            return False

        logger.info("Starting OAuth authentication flow")

        try:
            # Step 1: Create session
            self.session = fyersModel.SessionModel(
                client_id=self.config.client_id,
                secret_key=self.config.secret_key,
                redirect_uri=self.config.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )

            # Step 2: Generate auth code URL
            auth_url = self.session.generate_authcode()

            logger.info("Authorization URL generated")

            # Step 3: Display URL and instructions
            print("\n" + "=" * 80)
            print("FYERS AUTHENTICATION")
            print("=" * 80)
            print("\nSTEP 1: Copy the Authorization URL below")
            print("─" * 80)
            print(f"\n{auth_url}\n")
            print("─" * 80)

            # Optionally open browser
            if self.auto_open_browser:
                print("\nOpening browser automatically...")
                try:
                    import webbrowser
                    webbrowser.open(auth_url)
                    print(" Browser opened")
                except Exception as e:
                    print(f" Could not open browser: {e}")
                    print("Please copy the URL above manually")

            print("\nSTEP 2: Manual Steps")
            print("  1. Copy the URL above (or use the browser that opened)")
            print("  2. Paste it in your browser")
            print("  3. Log in to your Fyers account")
            print("  4. Authorize the application")
            print("  5. Copy the ENTIRE redirect URL from browser")

            print("\nThe redirect URL looks like:")
            print("  https://trade.fyers.in/api-login/redirect-to-app?auth_code=XXXXX&state=sample_state")
            print("\n" + "=" * 80)

            redirect_url = input("\nPaste the redirect URL here: ").strip()

            # Extract auth code
            auth_code = self._extract_auth_code(redirect_url)
            if not auth_code:
                logger.error("Failed to extract authorization code")
                return False

            # Step 4: Set auth code
            self.session.set_token(auth_code)

            # Step 5: Generate access token
            response = self.session.generate_token()

            if not self._validate_token_response(response):
                return False

            # Extract tokens
            access_token = response['access_token']
            refresh_token = response.get('refresh_token', auth_code)  # Use auth_code as fallback

            # Store tokens in config
            self.config.access_token = access_token
            self.config.refresh_token = refresh_token

            # Save to .env file
            self._update_env_file()

            logger.info(" Authentication successful!")
            logger.info(" Tokens saved to .env file")

            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}", exc_info=True)
            return False

    def is_token_valid(self, access_token: str = None) -> bool:
        """Check if access token is still valid"""
        if not access_token or not self.client_id:
            return False

        try:
            headers = {'Authorization': f"{self.client_id}:{access_token}"}
            response = requests.get(self.profile_url, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                is_valid = result.get('s') == 'ok'
                logger.debug(f"Token validation result: {'valid' if is_valid else 'invalid'}")
                return is_valid
            else:
                logger.debug(f"Token validation failed with status: {response.status_code}")
                return False

        except Exception as e:
            logger.debug(f"Token validation error: {e}")
            return False

    def validate_token_with_api(self) -> bool:
        """
        Validate token by making a test API call to Fyers.

        Returns:
            bool: True if token works with Fyers API
        """
        if not self.config.access_token:
            logger.debug("No access token to validate")
            return False

        try:
            # Create Fyers client
            fyers = fyersModel.FyersModel(
                client_id=self.config.client_id,
                token=self.config.access_token,
                log_path="logs/"
            )

            # Try to get profile (lightweight API call)
            response = fyers.get_profile()

            if response and response.get('s') == 'ok':
                logger.info(" Token validated with Fyers API")
                return True
            else:
                logger.warning(" Token validation failed with Fyers API")
                return False

        except Exception as e:
            logger.error(f"Error validating token with API: {e}")
            return False

    def update_pin(self, new_pin: str) -> bool:
        """
        Update trading PIN in .env file.

        Args:
            new_pin: New 4-6 digit PIN

        Returns:
            bool: True if updated successfully
        """
        if not new_pin or not new_pin.isdigit() or len(new_pin) < 4 or len(new_pin) > 6:
            logger.error("Invalid PIN format (must be 4-6 digits)")
            return False

        self.config.pin = new_pin
        return self._update_env_file()

    def _extract_auth_code(self, redirect_url: str) -> Optional[str]:
        """Extract authorization code from redirect URL."""
        try:
            # Handle different URL formats
            if '?' not in redirect_url:
                logger.error(" Invalid redirect URL format (no query parameters)")
                return None

            parsed = urlparse(redirect_url)
            params = parse_qs(parsed.query)

            # Try 'auth_code' parameter
            auth_code = params.get('auth_code', [None])[0]

            if not auth_code:
                # Try alternative parameter names
                auth_code = params.get('code', [None])[0]

            if auth_code:
                logger.info(" Authorization code extracted successfully")
                logger.debug(f"Auth code (first 20 chars): {auth_code[:20]}...")
                return auth_code
            else:
                logger.error(" No auth_code or code parameter in URL")
                logger.error(f"  Available parameters: {list(params.keys())}")
                return None

        except Exception as e:
            logger.error(f"Error extracting auth code: {e}")
            return None

    def _validate_token_response(self, response: Dict) -> bool:
        """Validate token response from Fyers."""
        if not response:
            logger.error(" Empty response from Fyers")
            return False

        if response.get('s') != 'ok':
            error_msg = response.get('message', 'Unknown error')
            error_code = response.get('code', 'N/A')
            logger.error(f" Token generation failed: {error_msg} (Code: {error_code})")
            return False

        if 'access_token' not in response:
            logger.error(" No access token in response")
            logger.debug(f"Response keys: {list(response.keys())}")
            return False

        logger.info(" Token response validation passed")
        return True

    def _update_env_file(self) -> bool:
        """
        Update .env file with tokens.

        Returns:
            bool: True if updated successfully
        """
        env_file = Path('.env')

        if not env_file.exists():
            logger.warning(".env file not found, creating new one")
            template = Path('.env.template')
            if template.exists():
                import shutil
                shutil.copy(template, env_file)
            else:
                # Create minimal .env file
                with open(env_file, 'w') as f:
                    f.write(f"# Fyers API Configuration\n")
                    f.write(f"FYERS_CLIENT_ID={self.config.client_id}\n")
                    f.write(f"FYERS_SECRET_KEY={self.config.secret_key}\n")
                    f.write(f"FYERS_REDIRECT_URI={self.config.redirect_uri}\n")

        try:
            # Read current .env
            with open(env_file, 'r') as f:
                lines = f.readlines()

            # Track what we've updated
            updated = {
                'access_token': False,
                'refresh_token': False,
                'pin': False
            }

            new_lines = []

            for line in lines:
                if line.startswith('FYERS_ACCESS_TOKEN='):
                    new_lines.append(f'FYERS_ACCESS_TOKEN={self.config.access_token}\n')
                    updated['access_token'] = True
                elif line.startswith('FYERS_REFRESH_TOKEN='):
                    new_lines.append(f'FYERS_REFRESH_TOKEN={self.config.refresh_token}\n')
                    updated['refresh_token'] = True
                elif line.startswith('FYERS_PIN=') and self.config.pin:
                    new_lines.append(f'FYERS_PIN={self.config.pin}\n')
                    updated['pin'] = True
                else:
                    # Keep all other lines as-is (including FYERS_CLIENT_ID, etc.)
                    new_lines.append(line)

            # Add missing entries
            if not updated['access_token']:
                new_lines.append(f'FYERS_ACCESS_TOKEN={self.config.access_token}\n')
            if not updated['refresh_token']:
                new_lines.append(f'FYERS_REFRESH_TOKEN={self.config.refresh_token}\n')
            if not updated['pin'] and self.config.pin:
                new_lines.append(f'FYERS_PIN={self.config.pin}\n')

            # Write back
            with open(env_file, 'w') as f:
                f.writelines(new_lines)

            logger.info(" .env file updated with tokens")
            return True

        except Exception as e:
            logger.error(f"Error updating .env file: {e}")
            return False

    def clear_tokens(self) -> bool:
        """Clear tokens from .env file."""
        try:
            # Clear .env file
            env_file = Path('.env')

            if env_file.exists():
                with open(env_file, 'r') as f:
                    lines = f.readlines()

                new_lines = []
                for line in lines:
                    if line.startswith('FYERS_ACCESS_TOKEN='):
                        new_lines.append('FYERS_ACCESS_TOKEN=\n')
                    elif line.startswith('FYERS_REFRESH_TOKEN='):
                        new_lines.append('FYERS_REFRESH_TOKEN=\n')
                    else:
                        new_lines.append(line)

                with open(env_file, 'w') as f:
                    f.writelines(new_lines)

            # Clear config
            self.config.access_token = None
            self.config.refresh_token = None

            logger.info(" Tokens cleared from .env")
            return True

        except Exception as e:
            logger.error(f"Error clearing tokens: {e}")
            return False

    def get_token_info(self) -> Dict:
        """Get basic information about current tokens."""
        return {
            'has_access_token': bool(self.config.access_token),
            'has_refresh_token': bool(self.config.refresh_token),
            'is_valid': self.is_token_valid()
        }

    def print_token_info(self) -> None:
        """Print formatted token information."""
        info = self.get_token_info()

        print("\n" + "=" * 70)
        print("FYERS AUTHENTICATION STATUS")
        print("=" * 70)

        # Status
        status = " VALID" if info['is_valid'] else " NOT AUTHENTICATED"

        print(f"\nStatus: {status}")
        print(f"Access Token: {' Present' if info['has_access_token'] else ' Missing'}")
        print(f"Refresh Token: {' Present' if info['has_refresh_token'] else ' Missing'}")

        # Recommendations
        if not info['is_valid']:
            print("\n Action Required:")
            print("  Run: python main.py auth")

        print("\n" + "=" * 70)


    def get_valid_access_token(self) -> Optional[str]:
        """Get a valid access token, using refresh token if available"""
        try:
            # First, check if current access token is still valid
            if self.access_token and self.is_token_valid(self.access_token):
                logger.info("Current access token is still valid")
                return self.access_token

            logger.info("Access token is invalid or expired")

            # Try to use refresh token if available
            if self.refresh_token:
                logger.info("Attempting to refresh access token...")
                new_access_token, new_refresh_token = self.generate_access_token_with_refresh(self.refresh_token)

                if new_access_token:
                    logger.info("Successfully refreshed access token")

                    # Save new tokens
                    self.save_to_env('FYERS_ACCESS_TOKEN', new_access_token)
                    self.access_token = new_access_token

                    if new_refresh_token:
                        self.save_to_env('FYERS_REFRESH_TOKEN', new_refresh_token)
                        self.refresh_token = new_refresh_token

                    return new_access_token
                else:
                    logger.warning("Failed to refresh access token")

            # If refresh failed or no refresh token, require full authentication
            logger.info("Full re-authentication required")
            return self.setup_full_authentication()

        except Exception as e:
            logger.error(f"Error getting valid access token: {e}")
            return None

# Convenience functions
def authenticate_fyers(config_dict: dict) -> bool:
    """Handle Fyers authentication with refresh token and PIN support"""
    try:
        auth_manager = FyersAuthenticationHelper()

        # Get valid access token (will auto-refresh if needed)
        access_token = auth_manager.get_valid_access_token()

        if access_token:
            # Update config with the valid token
            config_dict['fyers_config'].access_token = access_token
            logger.info("Fyers authentication successful")
            return True
        else:
            logger.error("Fyers authentication failed")
            return False

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return False


def ensure_authenticated(config: Optional[FyersConfig] = None) -> bool:
    """
    Ensure valid authentication.
    
    Simply checks if token exists - matches FyersORB behavior.
    """
    if config is None:
        from config.settings import config as app_config
        config = app_config.fyers

    helper = FyersAuthenticationHelper(config)
    return helper.is_token_valid()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from config.settings import config

    auth_helper = FyersAuthenticationHelper(config.fyers)
    auth_helper.print_token_info()

    if not auth_helper.is_token_valid():
        print("\n Authentication required...")
        success = auth_helper.authenticate()

        if success:
            print("\n Authentication successful!")
            auth_helper.print_token_info()
        else:
            print("\n Authentication failed")
    else:
        print("\n Already authenticated")