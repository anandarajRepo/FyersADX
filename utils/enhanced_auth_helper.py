"""
Enhanced Authentication Helper for Fyers API.

Handles OAuth flow, token management, and automatic token refresh with PIN support.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from urllib.parse import parse_qs, urlparse

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
    Enhanced authentication helper with auto-refresh and secure token management.

    Features:
    - OAuth 2.0 flow
    - Automatic token refresh
    - Secure token storage
    - PIN-based authentication
    - Token validation
    """

    TOKEN_FILE = ".fyers_tokens.json"
    TOKEN_VALIDITY_DAYS = 1  # Fyers tokens valid for 1 day

    def __init__(self, config: FyersConfig):
        """
        Initialize authentication helper.

        Args:
            config: FyersConfig object
        """
        self.config = config
        self.session = None
        self.token_file_path = Path(self.TOKEN_FILE)
        self.auto_open_browser = False  # Default: don't auto-open browser

        logger.info("Initialized FyersAuthenticationHelper")

    def authenticate(self) -> bool:
        """
        Perform complete authentication flow.

        Returns:
            bool: True if authentication successful
        """
        if not FYERS_AVAILABLE:
            logger.error("Fyers API not available")
            return False

        # Check if we have valid cached tokens
        if self._load_cached_tokens():
            logger.info("Using cached authentication tokens")
            return True

        # Perform OAuth flow
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

            logger.info(f"Authorization URL generated")

            # Step 3: Display URL and instructions
            print("\n" + "=" * 80)
            print("FYERS AUTHENTICATION")
            print("=" * 80)
            print("\n STEP 1: Copy the Authorization URL below")
            print("─" * 80)
            print(f"\n{auth_url}\n")
            print("─" * 80)

            # Optionally open browser
            if self.auto_open_browser:
                print("\n Opening browser automatically...")
                try:
                    import webbrowser
                    webbrowser.open(auth_url)
                    print("✓ Browser opened")
                except Exception as e:
                    print(f"✗ Could not open browser: {e}")
                    print("Please copy the URL above manually")

            print("\nSTEP 2: Manual Steps")
            print("  1. Copy the URL above (or use the browser that opened)")
            print("  2. Paste it in your browser (if not auto-opened)")
            print("  3. Log in to your Fyers account")
            print("  4. Authorize the application")
            print("  5. You will be redirected (page may show 'site cannot be reached')")
            print("  6. Copy the ENTIRE redirect URL from browser address bar")

            print("\n The redirect URL should look like:")
            print("  http://localhost:8000/callback?auth_code=XXXXX&state=sample_state")
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

            # Store tokens
            self.config.access_token = response['access_token']
            self.config.refresh_token = response.get('refresh_token', '')

            # Save tokens
            self._save_tokens()

            # Update .env file
            self._update_env_file()

            logger.info("Authentication successful!")
            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def refresh_token(self) -> bool:
        """
        Refresh access token using refresh token.

        Returns:
            bool: True if refresh successful
        """
        if not self.config.refresh_token:
            logger.warning("No refresh token available")
            return self.authenticate()

        try:
            logger.info("Refreshing access token...")

            # Create session for refresh
            session = fyersModel.SessionModel(
                client_id=self.config.client_id,
                secret_key=self.config.secret_key,
                redirect_uri=self.config.redirect_uri,
                response_type="code",
                grant_type="refresh_token"
            )

            # Set refresh token
            session.set_token(self.config.refresh_token)

            # Generate new access token
            response = session.generate_token()

            if not self._validate_token_response(response):
                logger.error("Token refresh failed, re-authenticating...")
                return self.authenticate()

            # Update tokens
            self.config.access_token = response['access_token']
            if 'refresh_token' in response:
                self.config.refresh_token = response['refresh_token']

            # Save tokens
            self._save_tokens()
            self._update_env_file()

            logger.info("Token refreshed successfully")
            return True

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return self.authenticate()

    def is_token_valid(self) -> bool:
        """
        Check if current token is valid.

        Returns:
            bool: True if token is valid
        """
        if not self.config.access_token:
            return False

        # Check token expiry from cache
        token_data = self._load_token_data()
        if token_data:
            created_at = datetime.fromisoformat(token_data['created_at'])
            expiry = created_at + timedelta(days=self.TOKEN_VALIDITY_DAYS)

            if datetime.now() < expiry:
                logger.debug("Token is valid")
                return True
            else:
                logger.info("Token expired, need refresh")
                return False

        return False

    def ensure_valid_token(self) -> bool:
        """
        Ensure we have a valid access token (refresh if needed).

        Returns:
            bool: True if valid token available
        """
        if self.is_token_valid():
            return True

        logger.info("Token needs refresh")
        return self.refresh_token()

    def update_pin(self, new_pin: str) -> bool:
        """
        Update trading PIN.

        Args:
            new_pin: New 4-6 digit PIN

        Returns:
            bool: True if updated successfully
        """
        if not new_pin or not new_pin.isdigit() or len(new_pin) < 4:
            logger.error("Invalid PIN format")
            return False

        self.config.pin = new_pin

        # Update .env file
        return self._update_env_file()

    def _extract_auth_code(self, redirect_url: str) -> Optional[str]:
        """Extract authorization code from redirect URL."""
        try:
            parsed = urlparse(redirect_url)
            params = parse_qs(parsed.query)

            auth_code = params.get('auth_code', [None])[0]

            if auth_code:
                logger.info("Authorization code extracted successfully")
                return auth_code
            else:
                logger.error("No auth_code parameter found in URL")
                return None

        except Exception as e:
            logger.error(f"Error extracting auth code: {e}")
            return None

    def _validate_token_response(self, response: Dict) -> bool:
        """Validate token response from Fyers."""
        if not response:
            logger.error("Empty response from Fyers")
            return False

        if response.get('s') != 'ok':
            error_msg = response.get('message', 'Unknown error')
            logger.error(f"Token generation failed: {error_msg}")
            return False

        if 'access_token' not in response:
            logger.error("No access token in response")
            return False

        return True

    def _save_tokens(self) -> bool:
        """Save tokens to cache file."""
        try:
            token_data = {
                'access_token': self.config.access_token,
                'refresh_token': self.config.refresh_token,
                'created_at': datetime.now().isoformat(),
                'client_id': self.config.client_id
            }

            with open(self.token_file_path, 'w') as f:
                json.dump(token_data, f, indent=2)

            # Make file read-only for security
            self.token_file_path.chmod(0o600)

            logger.info("Tokens saved to cache")
            return True

        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
            return False

    def _load_cached_tokens(self) -> bool:
        """Load tokens from cache if valid."""
        token_data = self._load_token_data()

        if not token_data:
            return False

        # Check if tokens are for current client
        if token_data.get('client_id') != self.config.client_id:
            logger.warning("Cached tokens are for different client")
            return False

        # Check expiry
        try:
            created_at = datetime.fromisoformat(token_data['created_at'])
            expiry = created_at + timedelta(days=self.TOKEN_VALIDITY_DAYS)

            if datetime.now() >= expiry:
                logger.info("Cached tokens expired")
                return False
        except Exception as e:
            logger.error(f"Error checking token expiry: {e}")
            return False

        # Load tokens
        self.config.access_token = token_data['access_token']
        self.config.refresh_token = token_data.get('refresh_token', '')

        logger.info("Loaded valid cached tokens")
        return True

    def _load_token_data(self) -> Optional[Dict]:
        """Load token data from cache file."""
        if not self.token_file_path.exists():
            return None

        try:
            with open(self.token_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading token data: {e}")
            return None

    def _update_env_file(self) -> bool:
        """Update .env file with new tokens."""
        env_file = Path('.env')

        if not env_file.exists():
            logger.warning(".env file not found")
            return False

        try:
            # Read current .env
            with open(env_file, 'r') as f:
                lines = f.readlines()

            # Update relevant lines
            updated_lines = []
            found_access = False
            found_refresh = False
            found_pin = False

            for line in lines:
                if line.startswith('FYERS_ACCESS_TOKEN='):
                    updated_lines.append(f'FYERS_ACCESS_TOKEN={self.config.access_token}\n')
                    found_access = True
                elif line.startswith('FYERS_REFRESH_TOKEN='):
                    updated_lines.append(f'FYERS_REFRESH_TOKEN={self.config.refresh_token}\n')
                    found_refresh = True
                elif line.startswith('FYERS_PIN=') and self.config.pin:
                    updated_lines.append(f'FYERS_PIN={self.config.pin}\n')
                    found_pin = True
                else:
                    updated_lines.append(line)

            # Add if not found
            if not found_access:
                updated_lines.append(f'FYERS_ACCESS_TOKEN={self.config.access_token}\n')
            if not found_refresh:
                updated_lines.append(f'FYERS_REFRESH_TOKEN={self.config.refresh_token}\n')

            # Write back
            with open(env_file, 'w') as f:
                f.writelines(updated_lines)

            logger.info(".env file updated with new tokens")
            return True

        except Exception as e:
            logger.error(f"Error updating .env file: {e}")
            return False

    def clear_tokens(self) -> bool:
        """Clear all stored tokens."""
        try:
            if self.token_file_path.exists():
                self.token_file_path.unlink()

            self.config.access_token = None
            self.config.refresh_token = None

            logger.info("Tokens cleared")
            return True

        except Exception as e:
            logger.error(f"Error clearing tokens: {e}")
            return False

    def get_token_info(self) -> Dict:
        """
        Get information about current tokens.

        Returns:
            Dict with token information
        """
        token_data = self._load_token_data()

        info = {
            'has_access_token': bool(self.config.access_token),
            'has_refresh_token': bool(self.config.refresh_token),
            'is_valid': self.is_token_valid(),
            'created_at': None,
            'expires_at': None,
            'time_until_expiry': None
        }

        if token_data:
            try:
                created_at = datetime.fromisoformat(token_data['created_at'])
                expires_at = created_at + timedelta(days=self.TOKEN_VALIDITY_DAYS)

                info['created_at'] = created_at.isoformat()
                info['expires_at'] = expires_at.isoformat()

                if datetime.now() < expires_at:
                    delta = expires_at - datetime.now()
                    info['time_until_expiry'] = str(delta)
            except Exception as e:
                logger.error(f"Error calculating token info: {e}")

        return info

    def print_token_info(self) -> None:
        """Print formatted token information."""
        info = self.get_token_info()

        print("\n" + "=" * 60)
        print("FYERS AUTHENTICATION STATUS")
        print("=" * 60)

        print(f"\nAccess Token: {'✓ Present' if info['has_access_token'] else '✗ Missing'}")
        print(f"Refresh Token: {'✓ Present' if info['has_refresh_token'] else '✗ Missing'}")
        print(f"Token Valid: {'✓ Yes' if info['is_valid'] else '✗ No'}")

        if info['created_at']:
            print(f"\nCreated: {info['created_at']}")
            print(f"Expires: {info['expires_at']}")
            if info['time_until_expiry']:
                print(f"Time Until Expiry: {info['time_until_expiry']}")

        print("\n" + "=" * 60)


# Convenience functions
def authenticate_fyers(config: Optional[FyersConfig] = None) -> bool:
    """
    Quick authentication function.

    Args:
        config: FyersConfig (loads from environment if None)

    Returns:
        bool: True if authentication successful
    """
    if config is None:
        from config.settings import config as app_config
        config = app_config.fyers

    helper = FyersAuthenticationHelper(config)
    return helper.authenticate()


def ensure_authenticated(config: Optional[FyersConfig] = None) -> bool:
    """
    Ensure valid authentication (refresh if needed).

    Args:
        config: FyersConfig (loads from environment if None)

    Returns:
        bool: True if authentication valid
    """
    if config is None:
        from config.settings import config as app_config
        config = app_config.fyers

    helper = FyersAuthenticationHelper(config)
    return helper.ensure_valid_token()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Load configuration
    from config.settings import config

    # Create helper
    auth_helper = FyersAuthenticationHelper(config.fyers)

    # Print current status
    auth_helper.print_token_info()

    # Authenticate if needed
    if not auth_helper.is_token_valid():
        print("\nAuthentication required...")
        success = auth_helper.authenticate()

        if success:
            print("\nAuthentication successful!")
            auth_helper.print_token_info()
        else:
            print("\nAuthentication failed")
    else:
        print("\nAlready authenticated")