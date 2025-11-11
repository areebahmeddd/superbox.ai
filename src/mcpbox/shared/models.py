from typing import Optional

from pydantic import BaseModel


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


# API Requests - Server
class CreateServerRequest(BaseModel):
    """Request model for creating a new MCP server"""

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
    """Request model for updating an MCP server"""

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


# API Requests - Payment
class CreateOrderRequest(BaseModel):
    """Request model for creating a payment order"""

    server_name: str
    amount: float
    currency: str


class VerifyPaymentRequest(BaseModel):
    """Request model for verifying a payment"""

    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    server_name: str
