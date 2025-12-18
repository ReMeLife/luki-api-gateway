"""
Wallet Routes for Solana Wallet Verification and Genesis NFT Entitlements

These endpoints handle:
- Wallet signature verification (prove ownership)
- Genesis LUKi NFT detection
- Persona entitlement mapping

Frontend Flow:
1. User connects Solana wallet (Phantom, Solflare, etc.)
2. Frontend requests a nonce from /wallet/nonce
3. User signs the nonce with their wallet
4. Frontend sends signature to /wallet/verify
5. On success, frontend receives persona IDs to use in chat
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import secrets
import time
from datetime import datetime, timedelta
import httpx

from luki_api.clients.wallet_client import (
    wallet_client,
    WalletVerificationRequest,
    WalletVerificationResponse,
    WalletEntitlements,
)
from luki_api.config import settings

router = APIRouter(prefix="/wallet", tags=["wallet"])
logger = logging.getLogger(__name__)

# In-memory nonce store with expiration
# In production, use Redis for distributed nonce storage
_nonce_store: Dict[str, Dict[str, Any]] = {}
NONCE_TTL_SECONDS = 300  # 5 minutes


class NonceRequest(BaseModel):
    """Request for a verification nonce"""
    wallet_address: str = Field(..., description="Solana wallet address (base58)")


class NonceResponse(BaseModel):
    """Response containing the nonce to sign"""
    nonce: str
    message: str  # Full message to sign
    expires_at: str  # ISO timestamp


class VerifyRequest(BaseModel):
    """Request to verify wallet ownership"""
    wallet_address: str = Field(..., description="Solana wallet address")
    signature: str = Field(..., description="Base64 or Base58 encoded signature")
    nonce: str = Field(..., description="The nonce that was signed")


class VerifyResponse(BaseModel):
    """Response from wallet verification"""
    verified: bool
    wallet_address: str
    genesis_personas: List[str] = []
    default_persona: Optional[str] = None
    avatar_assets: Dict[str, str] = {}
    error: Optional[str] = None


class EntitlementsResponse(BaseModel):
    """Full entitlements for a verified wallet"""
    wallet_address: str
    genesis_personas: List[str]
    default_persona: Optional[str] = None
    avatar_assets: Dict[str, str] = {}
    nft_count: int = 0


def _cleanup_expired_nonces():
    """Remove expired nonces from store"""
    now = time.time()
    expired = [
        addr for addr, data in _nonce_store.items()
        if data.get("expires_at", 0) < now
    ]
    for addr in expired:
        del _nonce_store[addr]


def _generate_sign_message(wallet_address: str, nonce: str) -> str:
    """Generate the full message for the wallet to sign"""
    return (
        f"Sign this message to verify your wallet ownership for LUKi.\n\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}\n\n"
        f"This will not cost any SOL or trigger a transaction."
    )


@router.post("/nonce", response_model=NonceResponse)
async def get_verification_nonce(request: NonceRequest):
    """
    Get a nonce for wallet signature verification.
    
    The frontend should:
    1. Call this endpoint with the wallet address
    2. Have the user sign the returned message
    3. Submit the signature to /wallet/verify
    
    Nonces expire after 5 minutes.
    """
    _cleanup_expired_nonces()
    
    # Generate cryptographically secure nonce
    nonce = secrets.token_urlsafe(32)
    expires_at = time.time() + NONCE_TTL_SECONDS
    
    # Build the message to sign
    message = _generate_sign_message(request.wallet_address, nonce)
    
    # Store nonce for verification
    _nonce_store[request.wallet_address] = {
        "nonce": nonce,
        "message": message,
        "expires_at": expires_at,
        "created_at": time.time()
    }
    
    logger.info(f"Generated nonce for wallet: {request.wallet_address[:8]}...")
    
    return NonceResponse(
        nonce=nonce,
        message=message,
        expires_at=datetime.utcfromtimestamp(expires_at).isoformat() + "Z"
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_wallet(request: VerifyRequest):
    """
    Verify wallet ownership via signature.
    
    On successful verification, returns:
    - List of Genesis LUKi personas the wallet owns
    - Default persona (first owned)
    - Avatar asset URLs for each persona
    
    The returned persona IDs can be passed to the chat endpoint
    as `context.persona_id` to activate that persona.
    """
    _cleanup_expired_nonces()
    
    # Check if we have a valid nonce for this wallet
    stored = _nonce_store.get(request.wallet_address)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending nonce for this wallet. Request a new nonce first."
        )
    
    if stored["nonce"] != request.nonce:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid nonce"
        )
    
    if stored["expires_at"] < time.time():
        del _nonce_store[request.wallet_address]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nonce expired. Request a new one."
        )
    
    # Verify signature using the stored message
    wallet_request = WalletVerificationRequest(
        wallet_address=request.wallet_address,
        signature=request.signature,
        message=stored["message"]
    )
    
    try:
        result = await wallet_client.verify_and_get_entitlements(wallet_request)
    except Exception as e:
        logger.error(f"Wallet verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed. Please try again."
        )
    
    # Clean up used nonce
    del _nonce_store[request.wallet_address]
    
    if not result.verified:
        return VerifyResponse(
            verified=False,
            wallet_address=request.wallet_address,
            error=result.error or "Signature verification failed"
        )
    
    # Get full entitlements for avatar assets
    try:
        entitlements = await wallet_client.get_wallet_entitlements(request.wallet_address)
    except Exception as e:
        logger.warning(f"Failed to get full entitlements: {e}")
        entitlements = None
    
    logger.info(
        f"Wallet verified: {request.wallet_address[:8]}... "
        f"with {len(result.genesis_personas)} personas"
    )
    
    return VerifyResponse(
        verified=True,
        wallet_address=request.wallet_address,
        genesis_personas=result.genesis_personas,
        default_persona=result.genesis_personas[0] if result.genesis_personas else None,
        avatar_assets=entitlements.avatar_assets if entitlements else {}
    )


@router.get("/entitlements/{wallet_address}", response_model=EntitlementsResponse)
async def get_wallet_entitlements(wallet_address: str):
    """
    Get entitlements for a wallet address.
    
    This is a read-only endpoint that doesn't require signature verification.
    It returns what Genesis personas a wallet *would* have access to.
    
    Note: For security, sensitive actions should use the /verify flow
    which requires signature proof.
    """
    try:
        entitlements = await wallet_client.get_wallet_entitlements(wallet_address)
    except Exception as e:
        logger.error(f"Error getting entitlements: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve entitlements"
        )
    
    return EntitlementsResponse(
        wallet_address=wallet_address,
        genesis_personas=entitlements.genesis_personas,
        default_persona=entitlements.default_persona,
        avatar_assets=entitlements.avatar_assets,
        nft_count=len(entitlements.genesis_nfts)
    )


@router.get("/health")
async def wallet_health():
    """Health check for wallet service"""
    return {
        "status": "ok",
        "helius_configured": bool(wallet_client.helius_url),
        "genesis_collection_configured": bool(wallet_client.genesis_collection),
        "pending_nonces": len(_nonce_store)
    }


# =============================================================================
# WALLET ENCRYPTION ENDPOINTS (Proxy to Security Service)
# =============================================================================

class EncryptionChallengeResponse(BaseModel):
    """Response containing the challenge message to sign for encryption"""
    challenge: Dict[str, Any]
    instructions: str


class WalletEncryptionRegisterRequest(BaseModel):
    """Request to register wallet for encryption"""
    user_id: str
    wallet_public_key: str = Field(..., description="Solana public key (base58)")
    signature: str = Field(..., description="Signature of challenge message (base64)")


class WalletEncryptionDeriveRequest(BaseModel):
    """Request to derive a new session key"""
    user_id: str
    wallet_public_key: str
    signature: str


def _get_security_service_url() -> str:
    """Get the security service URL"""
    return getattr(settings, "SECURITY_SERVICE_URL", None) or "http://localhost:8103"


@router.get("/encryption/challenge/{user_id}")
async def get_encryption_challenge(user_id: str):
    """
    Get the challenge message for wallet encryption registration.
    
    The user must sign this message with their Solana wallet to prove ownership
    and enable wallet-derived encryption for their ELR data.
    """
    security_url = _get_security_service_url()
    url = f"{security_url.rstrip('/')}/wallet/challenge/{user_id}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Security service error: {response.status_code}")
            raise HTTPException(
                status_code=response.status_code,
                detail=response.json() if response.text else "Failed to get challenge"
            )
    except httpx.RequestError as e:
        logger.error(f"Security service request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security service unavailable"
        )


@router.post("/encryption/register")
async def register_wallet_encryption(request: WalletEncryptionRegisterRequest):
    """
    Register a Solana wallet for encryption key derivation.
    
    After registration, the user's ELR memories will be encrypted with
    a key derived from their wallet signature - only they can decrypt.
    """
    security_url = _get_security_service_url()
    url = f"{security_url.rstrip('/')}/wallet/register"
    
    payload = {
        "user_id": request.user_id,
        "wallet_public_key": request.wallet_public_key,
        "signature": request.signature,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
        
        data = response.json()
        
        if response.status_code == 200:
            logger.info(
                f"Wallet registered for encryption: user={request.user_id}, "
                f"wallet={request.wallet_public_key[:8]}..."
            )
            return data
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=data.get("detail", data)
            )
    except httpx.RequestError as e:
        logger.error(f"Security service request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security service unavailable"
        )


@router.post("/encryption/derive-key")
async def derive_encryption_key(request: WalletEncryptionDeriveRequest):
    """
    Derive a new session encryption key from wallet signature.
    
    Called when user needs to access their encrypted data.
    The derived key is cached in memory for the session duration.
    """
    security_url = _get_security_service_url()
    url = f"{security_url.rstrip('/')}/wallet/derive-key"
    
    payload = {
        "user_id": request.user_id,
        "wallet_public_key": request.wallet_public_key,
        "signature": request.signature,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
        
        data = response.json()
        
        if response.status_code == 200:
            return data
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=data.get("detail", data)
            )
    except httpx.RequestError as e:
        logger.error(f"Security service request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security service unavailable"
        )


@router.get("/encryption/status/{user_id}")
async def get_encryption_status(user_id: str):
    """
    Get wallet encryption status for a user.
    
    Returns whether wallet encryption is enabled, registered wallet info,
    and whether there's an active session key.
    """
    security_url = _get_security_service_url()
    url = f"{security_url.rstrip('/')}/wallet/status/{user_id}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            # Return default status if security service fails
            return {
                "user_id": user_id,
                "encryption_mode": "server",
                "wallet_registered": False,
                "has_active_session_key": False,
            }
    except httpx.RequestError as e:
        logger.warning(f"Security service request failed: {e}")
        return {
            "user_id": user_id,
            "encryption_mode": "server",
            "wallet_registered": False,
            "has_active_session_key": False,
        }
