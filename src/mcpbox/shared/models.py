from typing import Optional

from pydantic import BaseModel, EmailStr


# Core Entities
class Repository(BaseModel):
    """Git repository information"""

    type: str
    url: str


class Pricing(BaseModel):
    """Pricing information for MCP servers"""

    currency: str
    amount: float


class ToolInfo(BaseModel):
    """MCP tool discovery information"""

    count: int
    names: list[str]


class Meta(BaseModel):
    """Metadata timestamps"""

    created_at: str
    updated_at: str


class MCPServer(BaseModel):
    """Complete MCP Server definition"""

    name: str
    version: str
    description: str
    author: str
    lang: str
    license: str
    entrypoint: str
    repository: Repository
    pricing: Optional[Pricing] = None
    tools: Optional[dict] = None
    security_report: Optional[dict] = None
    meta: Optional[Meta] = None


# Server API Models
class CreateServerRequest(BaseModel):
    """Request payload for creating an MCP server"""

    name: str
    version: str
    description: str
    author: str
    lang: str
    license: str
    entrypoint: str
    repository: Repository
    pricing: Pricing
    tools: Optional[dict] = None


class UpdateServerRequest(BaseModel):
    """Request payload for updating an MCP server"""

    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    lang: Optional[str] = None
    license: Optional[str] = None
    entrypoint: Optional[str] = None
    repository: Optional[Repository] = None
    pricing: Optional[Pricing] = None
    tools: Optional[dict] = None
    security_report: Optional[dict] = None


# Auth API Models
class AuthRegisterRequest(BaseModel):
    """Request payload for registering a new user"""

    email: EmailStr
    password: str
    display_name: Optional[str] = None


class AuthLoginRequest(BaseModel):
    """Request payload for logging in a user"""

    email: EmailStr
    password: str


class AuthProviderRequest(BaseModel):
    """Request payload for logging in via OAuth providers"""

    provider: str
    id_token: Optional[str] = None
    access_token: Optional[str] = None


class AuthDeviceStartRequest(BaseModel):
    """Request payload to initiate an OAuth device login"""

    provider: str


class AuthDevicePollRequest(BaseModel):
    """Request payload for polling device login status"""

    device_code: str


class AuthRefreshRequest(BaseModel):
    """Request payload for refreshing an ID token"""

    refresh_token: str


class AuthUpdateRequest(BaseModel):
    """Request payload for updating user profile details"""

    display_name: Optional[str] = None
    password: Optional[str] = None


class AuthResponse(BaseModel):
    """Response payload returned after authentication operations"""

    id_token: str
    refresh_token: str
    expires_in: int
    email: Optional[str] = None
    local_id: Optional[str] = None


class AuthUserProfile(BaseModel):
    """Response payload for user profile lookup"""

    email: Optional[str] = None
    local_id: str
    display_name: Optional[str] = None
    email_verified: bool = False
    disabled: bool = False


# Payment API Models
class CreateOrderRequest(BaseModel):
    """Request payload for creating a Razorpay order"""

    server_name: str
    amount: float
    currency: str


class VerifyPaymentRequest(BaseModel):
    """Request payload for verifying a Razorpay payment"""

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    server_name: str
