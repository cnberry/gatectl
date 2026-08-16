class GatectlError(Exception):
    """Base error with a safe user-facing message."""


class MyQApiError(GatectlError):
    """MyQ returned an invalid or unsuccessful API response."""


class MyQAuthenticationError(GatectlError):
    """MyQ authentication failed or expired."""


class MyQInvalidCredentialsError(MyQAuthenticationError):
    """MyQ rejected the supplied email/password pair."""


class MyQInvalidMfaError(MyQAuthenticationError):
    """MyQ rejected the verification code."""


class MyQCloudflareChallengeError(MyQApiError):
    """MyQ returned a browser challenge instead of the login flow."""


class TokenStoreError(GatectlError):
    """The local token store is missing or invalid."""
