import hmac
import hashlib

import razorpay
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from mcpbox.shared.config import Config
from mcpbox.shared.models import CreateOrderRequest, VerifyPaymentRequest

router = APIRouter()

_cfg = Config()
razorpay_client = razorpay.Client(auth=(_cfg.RAZORPAY_KEY_ID, _cfg.RAZORPAY_KEY_SECRET))


@router.post("/create-order")
async def create_order(request: CreateOrderRequest) -> JSONResponse:
    """Create a Razorpay order for server purchase"""
    try:
        amount_in_subunits = int(request.amount * 100)
        currency_upper = request.currency.upper()

        order_data = {
            "amount": amount_in_subunits,
            "currency": currency_upper,
            "receipt": f"order_{request.server_name}_{amount_in_subunits}",
            "notes": {"server_name": request.server_name},
        }

        order = razorpay_client.order.create(data=order_data)

        return JSONResponse(
            content={
                "status": "success",
                "order": {
                    "id": order["id"],
                    "amount": order["amount"],
                    "currency": order["currency"],
                },
                "key_id": _cfg.RAZORPAY_KEY_ID,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")


@router.post("/verify-payment")
async def verify_payment(request: VerifyPaymentRequest) -> JSONResponse:
    """Verify Razorpay payment signature"""
    try:
        generated_signature = hmac.new(
            _cfg.RAZORPAY_KEY_SECRET.encode(),
            f"{request.razorpay_order_id}|{request.razorpay_payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if generated_signature == request.razorpay_signature:
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "Payment verified",
                    "payment": {
                        "id": request.razorpay_payment_id,
                        "server_name": request.server_name,
                    },
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid payment signature")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying payment: {str(e)}")


@router.get("/payment-status/{payment_id}")
async def get_status(payment_id: str) -> JSONResponse:
    """Get payment status from Razorpay"""
    try:
        payment = razorpay_client.payment.fetch(payment_id)

        return JSONResponse(
            content={
                "status": "success",
                "payment": {
                    "id": payment["id"],
                    "state": payment["status"],
                    "amount": payment["amount"],
                    "currency": payment["currency"],
                    "method": payment.get("method"),
                    "email": payment.get("email"),
                    "contact": payment.get("contact"),
                },
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching payment status: {str(e)}")
