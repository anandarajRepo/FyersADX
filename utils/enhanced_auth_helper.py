"""
Enhanced Authentication Helper for Fyers API - Simplified Version.

Stores tokens ONLY in .env file (no JSON caching).
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
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
    Enhanced authentication helper with .env-only token storage.

    Features:
    - OAuth 2.0 flow
    - Secure token storage in .env
    - Token validation
    - PIN-based authentication
    """

    # No JSON file - tokens stored only in .env
    TOKEN_VALIDITY_HOURS = 24  # Fyers tokens valid for 24 hours

    def __init__(self, config: FyersConfig):
        """
        Initialize authentication helper.

        Args:
            config: FyersConfig object
        """
        self.config = config
        self.session = None
        self.auto_open_browser = False

        logger.info("Initialized FyersAuthenticationHelper (env-only mode)")

    def authenticate(self) -> bool:
        """
        Perform complete authentication flow.

        Returns:
            bool: True if authentication successful
        """
        if not FYERS_AVAILABLE:
            logger.error("Fyers API not available")
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

            logger.info(f"Authorization URL generated")

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
                    print("Browser opened")
                except Exception as e:
                    print(f"Could not open browser: {e}")
                    print("Please copy the URL above manually")

            print("\nSTEP 2: Manual Steps")
            print("  1. Copy the URL above (or use the browser that opened)")
            print("  2. Paste it in your browser")
            print("  3. Log in to your Fyers account")
            print("  4. Authorize the application")
            print("  5. Copy the ENTIRE redirect URL from browser")

            print("\nThe redirect URL looks like:")
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

            # Store tokens in config
            self.config.access_token = response['access_token']
            self.config.refresh_token = response.get('refresh_token', auth_code)

            # Save to .env file ONLY
            self._update_env_file()

            logger.info("Authentication successful!")
            logger.info("Tokens saved to .env file")

            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def is_token_valid(self) -> bool:
        """
        Check if current token exists and is likely valid.

        Note: Since we don't store creation time without JSON file,
        we just check if token exists in config.

        Returns:
            bool: True if token exists
        """
        if not self.config.access_token:
            logger.debug("No access token available")
            return False

        # Token exists - assume valid (Fyers tokens last 24 hours)
        # User will get API errors if actually expired
        logger.debug("Access token found")
        return True

    def ensure_valid_token(self) -> bool:
        """
        Ensure we have a valid access token.

        Note: Fyers doesn't support token refresh.
        Returns True if token exists, False if re-auth needed.

        Returns:
            bool: True if valid token available
        """
        if self.is_token_valid():
            logger.debug("Token is present")
            return True

        logger.warning("No valid token - re-authentication required")
        return False

    def update_pin(self, new_pin: str) -> bool:
        """
        Update trading PIN in .env file.

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

    def _update_env_file(self) -> bool:
        """
        Update .env file with tokens.

        This is the ONLY place tokens are stored.
        """
        env_file = Path('.env')

        if not env_file.exists():
            logger.warning(".env file not found, creating new one")
            # Create from template if exists
            template = Path('.env.template')
            if template.exists():
                import shutil
                shutil.copy(template, env_file)

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

            # Add missing entries
            if not found_access:
                updated_lines.append(f'FYERS_ACCESS_TOKEN={self.config.access_token}\n')
            if not found_refresh:
                updated_lines.append(f'FYERS_REFRESH_TOKEN={self.config.refresh_token}\n')

            # Write back
            with open(env_file, 'w') as f:
                f.writelines(updated_lines)

            logger.info("✓ Tokens updated in .env file")
            return True

        except Exception as e:
            logger.error(f"Error updating .env file: {e}")
            return False

    def clear_tokens(self) -> bool:
        """
        Clear tokens from .env file.
        """
        try:
            env_file = Path('.env')

            if not env_file.exists():
                logger.info("No .env file to clear")
                return True

            # Read current .env
            with open(env_file, 'r') as f:
                lines = f.readlines()

            # Clear token lines
            updated_lines = []
            for line in lines:
                if line.startswith('FYERS_ACCESS_TOKEN='):
                    updated_lines.append('FYERS_ACCESS_TOKEN=\n')
                elif line.startswith('FYERS_REFRESH_TOKEN='):
                    updated_lines.append('FYERS_REFRESH_TOKEN=\n')
                else:
                    updated_lines.append(line)

            # Write back
            with open(env_file, 'w') as f:
                f.writelines(updated_lines)

            # Clear from config
            self.config.access_token = None
            self.config.refresh_token = None

            logger.info("✓ Tokens cleared from .env")
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
        info = {
            'has_access_token': bool(self.config.access_token),
            'has_refresh_token': bool(self.config.refresh_token),
            'is_valid': self.is_token_valid(),
            'storage_location': '.env file',
            'note': 'Tokens stored only in .env (no JSON cache)'
        }

        return info

    def print_token_info(self) -> None:
        """Print formatted token information."""
        info = self.get_token_info()

        print("\n" + "=" * 60)
        print("FYERS AUTHENTICATION STATUS")
        print("=" * 60)

        print(f"\nAccess Token: {'Present' if info['has_access_token'] else 'Missing'}")
        print(f"Refresh Token: {'Present' if info['has_refresh_token'] else 'Missing'}")
        print(f"Token Valid: {'Yes' if info['is_valid'] else 'No'}")
        print(f"\nStorage: {info['storage_location']}")
        print(f"Note: {info['note']}")

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
    Ensure valid authentication.

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