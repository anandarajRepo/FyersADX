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
    Enhanced authentication helper with AUTOMATIC token refresh.

    Features:
    - OAuth 2.0 flow
    - Secure token storage in .env
    - Token validation with expiry tracking
    - AUTOMATIC token refresh using refresh token
    - PIN-based authentication
    - Token metadata storage
    """

    TOKEN_VALIDITY_HOURS = 24  # Fyers tokens valid for 24 hours
    REFRESH_BUFFER_HOURS = 1   # Refresh if within 1 hour of expiry
    TOKEN_METADATA_FILE = ".fyers_tokens.json"  # Stores token metadata

    def __init__(self, config: FyersConfig):
        """
        Initialize authentication helper.

        Args:
            config: FyersConfig object
        """
        self.config = config
        self.session = None
        self.auto_open_browser = False
        self.token_metadata = self._load_token_metadata()

        logger.info("Initialized FyersAuthenticationHelper with automatic token refresh")

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
                    print(f"✗ Could not open browser: {e}")
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

            # Save token metadata (includes timestamp)
            self._save_token_metadata(access_token, refresh_token, auth_code)

            # Save to .env file (tokens only, no timestamp)
            self._update_env_file()

            logger.info(" Authentication successful!")
            logger.info(" Tokens saved to .env file")
            logger.info(" Metadata saved to .fyers_tokens.json")

            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}", exc_info=True)
            return False

    def is_token_valid(self) -> bool:
        """
        Check if current token exists and is NOT expired.

        Returns:
            bool: True if token is valid and not expired
        """
        if not self.config.access_token:
            logger.debug("No access token available")
            return False

        # Check token expiry from metadata
        if not self.token_metadata:
            logger.warning("No token metadata found - assuming expired")
            return False

        created_at_str = self.token_metadata.get('created_at')
        if not created_at_str:
            logger.warning("No creation timestamp in metadata - assuming expired")
            return False

        try:
            created_at = datetime.fromisoformat(created_at_str)
            expiry_time = created_at + timedelta(hours=self.TOKEN_VALIDITY_HOURS)
            now = datetime.now()

            is_valid = now < expiry_time

            if is_valid:
                time_remaining = expiry_time - now
                hours_remaining = time_remaining.total_seconds() / 3600
                logger.debug(f"Token valid for {hours_remaining:.1f} more hours")
            else:
                time_expired = now - expiry_time
                hours_expired = time_expired.total_seconds() / 3600
                logger.warning(f"Token expired {hours_expired:.1f} hours ago")

            return is_valid

        except Exception as e:
            logger.error(f"Error checking token validity: {e}")
            return False

    def should_refresh_token(self) -> bool:
        """
        Check if token should be refreshed (within buffer period before expiry).

        Returns:
            bool: True if token should be refreshed
        """
        if not self.token_metadata:
            return True

        created_at_str = self.token_metadata.get('created_at')
        if not created_at_str:
            return True

        try:
            created_at = datetime.fromisoformat(created_at_str)
            expiry_time = created_at + timedelta(hours=self.TOKEN_VALIDITY_HOURS)
            refresh_threshold = expiry_time - timedelta(hours=self.REFRESH_BUFFER_HOURS)
            now = datetime.now()

            should_refresh = now >= refresh_threshold

            if should_refresh:
                logger.info(f"Token should be refreshed (within {self.REFRESH_BUFFER_HOURS}h buffer)")

            return should_refresh

        except Exception as e:
            logger.error(f"Error checking refresh requirement: {e}")
            return True

    def ensure_valid_token(self) -> bool:
        """
        Ensure we have a valid access token - REFRESH if needed.

        This is the KEY method that provides automatic token refresh.

        Returns:
            bool: True if valid token available (after refresh if needed)
        """
        # Check if current token is valid and doesn't need refresh
        if self.is_token_valid() and not self.should_refresh_token():
            logger.info(" Token is valid, no refresh needed")
            return True

        # Check if token is expired
        if not self.is_token_valid():
            logger.warning(" Token expired - attempting refresh...")
        else:
            logger.info(" Token approaching expiry - proactive refresh...")

        # Try to refresh the token
        if self.refresh_token():
            logger.info(" Token refreshed successfully")
            return True

        logger.error("✗ Token refresh failed - full re-authentication required")
        logger.error("  Run: python main.py auth")
        return False

    def refresh_token(self) -> bool:
        """
        Refresh the access token using the auth code.

        Fyers API v3 requires re-generation using the original auth code.

        Returns:
            bool: True if refresh successful
        """
        if not FYERS_AVAILABLE:
            logger.error("Fyers API not available")
            return False

        # Get auth code from metadata
        if not self.token_metadata or 'auth_code' not in self.token_metadata:
            logger.error("No auth code available for refresh - full re-authentication required")
            return False

        auth_code = self.token_metadata['auth_code']

        try:
            logger.info("Attempting to refresh access token...")

            # Create new session
            self.session = fyersModel.SessionModel(
                client_id=self.config.client_id,
                secret_key=self.config.secret_key,
                redirect_uri=self.config.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )

            # Use stored auth code to generate new token
            self.session.set_token(auth_code)

            # Generate new access token
            response = self.session.generate_token()

            if self._validate_token_response(response):
                # Extract new tokens
                access_token = response['access_token']
                refresh_token = response.get('refresh_token', auth_code)

                # Update config
                self.config.access_token = access_token
                self.config.refresh_token = refresh_token

                # Save new token metadata
                self._save_token_metadata(access_token, refresh_token, auth_code)

                # Update .env file
                self._update_env_file()

                logger.info(" Token refreshed successfully")
                return True
            else:
                logger.error("✗ Token refresh response invalid")
                return False

        except Exception as e:
            logger.error(f"Token refresh failed: {e}", exc_info=True)
            logger.warning(" Full re-authentication required")
            logger.warning("  Run: python main.py auth")
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
                logger.warning("✗ Token validation failed with Fyers API")
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
                logger.error("✗ Invalid redirect URL format (no query parameters)")
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
                logger.error("✗ No auth_code or code parameter in URL")
                logger.error(f"  Available parameters: {list(params.keys())}")
                return None

        except Exception as e:
            logger.error(f"Error extracting auth code: {e}")
            return None

    def _validate_token_response(self, response: Dict) -> bool:
        """Validate token response from Fyers."""
        if not response:
            logger.error("✗ Empty response from Fyers")
            return False

        if response.get('s') != 'ok':
            error_msg = response.get('message', 'Unknown error')
            error_code = response.get('code', 'N/A')
            logger.error(f"✗ Token generation failed: {error_msg} (Code: {error_code})")
            return False

        if 'access_token' not in response:
            logger.error("✗ No access token in response")
            logger.debug(f"Response keys: {list(response.keys())}")
            return False

        logger.info(" Token response validation passed")
        return True

    def _load_token_metadata(self) -> Dict:
        """
        Load token metadata from JSON file.

        Returns:
            Dict with token metadata or empty dict
        """
        metadata_file = Path(self.TOKEN_METADATA_FILE)

        if not metadata_file.exists():
            logger.debug("No token metadata file found")
            return {}

        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                logger.debug(" Token metadata loaded")
                return metadata
        except Exception as e:
            logger.error(f"Error loading token metadata: {e}")
            return {}

    def _save_token_metadata(self, access_token: str, refresh_token: str, auth_code: str) -> bool:
        """
        Save token metadata to JSON file.

        Args:
            access_token: Access token
            refresh_token: Refresh token
            auth_code: Original auth code (for refresh)

        Returns:
            bool: True if saved successfully
        """
        try:
            metadata = {
                'created_at': datetime.now().isoformat(),
                'access_token_preview': access_token[:20] + '...' if access_token else None,
                'refresh_token_preview': refresh_token[:20] + '...' if refresh_token else None,
                'auth_code': auth_code,  # Store for refresh
                'client_id': self.config.client_id,
                'expires_at': (datetime.now() + timedelta(hours=self.TOKEN_VALIDITY_HOURS)).isoformat()
            }

            metadata_file = Path(self.TOKEN_METADATA_FILE)

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Update in-memory metadata
            self.token_metadata = metadata

            logger.info(" Token metadata saved")
            return True

        except Exception as e:
            logger.error(f"Error saving token metadata: {e}")
            return False

    def _update_env_file(self) -> bool:
        """
        Update .env file with tokens only (no timestamps).

        Timestamps are stored in .fyers_tokens.json metadata file.

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
        """Clear tokens from .env file and metadata."""
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

            # Clear metadata file
            metadata_file = Path(self.TOKEN_METADATA_FILE)
            if metadata_file.exists():
                metadata_file.unlink()

            # Clear config
            self.config.access_token = None
            self.config.refresh_token = None
            self.token_metadata = {}

            logger.info(" Tokens cleared from .env and metadata")
            return True

        except Exception as e:
            logger.error(f"Error clearing tokens: {e}")
            return False

    def get_token_info(self) -> Dict:
        """Get comprehensive information about current tokens."""
        info = {
            'has_access_token': bool(self.config.access_token),
            'has_refresh_token': bool(self.config.refresh_token),
            'has_metadata': bool(self.token_metadata),
            'is_valid': False,
            'created_at': None,
            'expires_at': None,
            'token_age_hours': None,
            'expires_in_hours': None,
            'should_refresh': False
        }

        if self.token_metadata:
            created_at_str = self.token_metadata.get('created_at')
            expires_at_str = self.token_metadata.get('expires_at')

            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    info['created_at'] = created_at_str

                    # Calculate age
                    age = datetime.now() - created_at
                    info['token_age_hours'] = age.total_seconds() / 3600

                    # Calculate expiry
                    expiry = created_at + timedelta(hours=self.TOKEN_VALIDITY_HOURS)
                    info['expires_at'] = expiry.isoformat()

                    remaining = expiry - datetime.now()
                    info['expires_in_hours'] = remaining.total_seconds() / 3600

                    # Check validity
                    info['is_valid'] = remaining.total_seconds() > 0

                    # Check if should refresh
                    info['should_refresh'] = self.should_refresh_token()

                except Exception as e:
                    logger.error(f"Error calculating token info: {e}")

        return info

    def print_token_info(self) -> None:
        """Print formatted token information."""
        info = self.get_token_info()

        print("\n" + "=" * 70)
        print("FYERS AUTHENTICATION STATUS")
        print("=" * 70)

        # Status
        if info['is_valid']:
            status = " VALID"
            if info['should_refresh']:
                status += " (Refresh Recommended)"
        else:
            status = "✗ INVALID/EXPIRED"

        print(f"\nStatus: {status}")
        print(f"Access Token: {' Present' if info['has_access_token'] else '✗ Missing'}")
        print(f"Refresh Token: {' Present' if info['has_refresh_token'] else '✗ Missing'}")
        print(f"Metadata: {' Available' if info['has_metadata'] else '✗ Missing'}")

        # Timing information
        if info['created_at']:
            print(f"\nToken Created: {info['created_at']}")
            print(f"Token Age: {info['token_age_hours']:.1f} hours")

            if info['expires_in_hours']:
                if info['expires_in_hours'] > 0:
                    print(f"Expires In: {info['expires_in_hours']:.1f} hours")
                else:
                    print(f"Expired: {abs(info['expires_in_hours']):.1f} hours ago")

        # Recommendations
        print("\nRecommendations:")
        if not info['is_valid']:
            print("  • Token expired - refresh required")
            print("  • Run: python main.py auth (if refresh fails)")
        elif info['should_refresh']:
            print("  • Proactive refresh recommended")
            print("  • Token will be auto-refreshed on next strategy run")
        else:
            print("  •  No action needed - token is valid")

        print("\n" + "=" * 70)


# Convenience functions
def authenticate_fyers(config: Optional[FyersConfig] = None) -> bool:
    """Quick authentication function."""
    if config is None:
        from config.settings import config as app_config
        config = app_config.fyers

    helper = FyersAuthenticationHelper(config)
    return helper.authenticate()


def ensure_authenticated(config: Optional[FyersConfig] = None) -> bool:
    """
    Ensure valid authentication with AUTO-REFRESH.

    This is the KEY function to use before any Fyers API operations.
    """
    if config is None:
        from config.settings import config as app_config
        config = app_config.fyers

    helper = FyersAuthenticationHelper(config)
    return helper.ensure_valid_token()


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
            print("\n✗ Authentication failed")
    else:
        print("\n Already authenticated")