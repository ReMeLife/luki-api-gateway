"""
Wallet Client for Solana NFT Verification

This module provides functionality to verify Solana wallet ownership
and detect Genesis LUKi NFT holdings for persona entitlements.
"""

import httpx
import logging
import os
import base64
import json
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

logger = logging.getLogger(__name__)

# Solana network configuration (devnet or mainnet-beta)
# Use devnet for testing, mainnet-beta for production
SOLANA_NETWORK = os.getenv("SOLANA_NETWORK", "devnet")  # Default to devnet for testing

# Genesis LUKi NFT Collection configuration
GENESIS_COLLECTION_ADDRESS = os.getenv(
    "GENESIS_LUKI_COLLECTION_ADDRESS",
    "5nbtm61GoC6ZqFdZNDnXBmS18qjRYdK7rZcQfTdGgoCH"  # Devnet collection for testing
)

# Helius API for NFT queries (faster than raw RPC)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

# Network-aware RPC URLs
def get_helius_url() -> str:
    if not HELIUS_API_KEY:
        return ""
    if SOLANA_NETWORK == "devnet":
        return f"https://devnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    return f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

def get_solana_url() -> str:
    if SOLANA_NETWORK == "devnet":
        return "https://api.devnet.solana.com"
    return "https://api.mainnet-beta.solana.com"

HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", get_helius_url())
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", get_solana_url())


class WalletVerificationRequest(BaseModel):
    """Request format for wallet verification"""
    wallet_address: str
    signature: str  # Base58 or Base64 encoded signature
    message: str    # The message that was signed (usually a nonce)


class WalletVerificationResponse(BaseModel):
    """Response format for wallet verification"""
    verified: bool
    wallet_address: str
    genesis_personas: List[str]  # e.g., ["genesis-1", "genesis-345"]
    error: Optional[str] = None


class NFTHolding(BaseModel):
    """Represents an NFT held by a wallet"""
    mint_address: str
    name: Optional[str] = None
    collection_address: Optional[str] = None
    token_id: Optional[int] = None
    metadata_uri: Optional[str] = None


class WalletEntitlements(BaseModel):
    """Entitlements derived from wallet holdings"""
    wallet_address: str
    genesis_personas: List[str]
    genesis_nfts: List[NFTHolding]
    default_persona: Optional[str] = None
    avatar_assets: Dict[str, str] = {}  # persona_id -> avatar_url


class WalletClient:
    """Client for Solana wallet verification and NFT detection"""
    
    def __init__(self):
        self.helius_url = HELIUS_RPC_URL
        self.solana_url = SOLANA_RPC_URL
        self.genesis_collection = GENESIS_COLLECTION_ADDRESS
        self.client = httpx.AsyncClient(timeout=30.0)
        
        if HELIUS_API_KEY:
            logger.info("WalletClient initialized with Helius RPC")
        else:
            logger.warning("WalletClient using public Solana RPC (rate limited)")
    
    async def verify_signature(
        self,
        wallet_address: str,
        signature: str,
        message: str
    ) -> bool:
        """
        Verify that a signature was created by the wallet's private key.
        
        This uses Ed25519 signature verification (Solana's signature scheme).
        
        Args:
            wallet_address: Base58 encoded Solana public key
            signature: Base64 or Base58 encoded signature
            message: The original message that was signed
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Import base58 for Solana address decoding
            import base58
            
            # Decode the wallet address (public key)
            try:
                public_key_bytes = base58.b58decode(wallet_address)
            except Exception as e:
                logger.error(f"Invalid wallet address format: {e}")
                return False
            
            # Decode the signature (try base64 first, then base58)
            try:
                signature_bytes = base64.b64decode(signature)
            except Exception:
                try:
                    signature_bytes = base58.b58decode(signature)
                except Exception as e:
                    logger.error(f"Invalid signature format: {e}")
                    return False
            
            # Create verify key and verify signature
            verify_key = VerifyKey(public_key_bytes)
            
            # The message should be encoded as bytes
            message_bytes = message.encode('utf-8')
            
            # Verify the signature
            verify_key.verify(message_bytes, signature_bytes)
            
            logger.info(f"Signature verified for wallet: {wallet_address[:8]}...")
            return True
            
        except BadSignatureError:
            logger.warning(f"Invalid signature for wallet: {wallet_address[:8]}...")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    async def get_nft_holdings(
        self,
        wallet_address: str,
        collection_filter: Optional[str] = None
    ) -> List[NFTHolding]:
        """
        Get NFT holdings for a wallet address.
        
        Uses Helius DAS API if available, falls back to basic RPC.
        
        Args:
            wallet_address: Solana wallet address
            collection_filter: Optional collection address to filter by
            
        Returns:
            List of NFT holdings
        """
        holdings: List[NFTHolding] = []
        
        # Use Helius DAS API for efficient NFT queries
        if HELIUS_API_KEY:
            holdings = await self._get_nfts_helius(wallet_address, collection_filter)
        else:
            holdings = await self._get_nfts_basic_rpc(wallet_address)
            
            # Filter by collection if specified
            if collection_filter:
                holdings = [
                    h for h in holdings 
                    if h.collection_address == collection_filter
                ]
        
        return holdings
    
    async def _get_nfts_helius(
        self,
        wallet_address: str,
        collection_filter: Optional[str] = None
    ) -> List[NFTHolding]:
        """Get NFTs using Helius Digital Asset Standard (DAS) API"""
        try:
            # Helius getAssetsByOwner endpoint
            payload = {
                "jsonrpc": "2.0",
                "id": "get-assets",
                "method": "getAssetsByOwner",
                "params": {
                    "ownerAddress": wallet_address,
                    "page": 1,
                    "limit": 1000,
                    "displayOptions": {
                        "showCollectionMetadata": True
                    }
                }
            }
            
            response = await self.client.post(
                self.helius_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            holdings: List[NFTHolding] = []
            
            items = data.get("result", {}).get("items", [])
            for item in items:
                # Skip fungible tokens
                if item.get("interface") != "V1_NFT" and item.get("interface") != "ProgrammableNFT":
                    continue
                
                collection_info = item.get("grouping", [])
                collection_address = None
                for group in collection_info:
                    if group.get("group_key") == "collection":
                        collection_address = group.get("group_value")
                        break
                
                # Filter by collection if specified
                if collection_filter and collection_address != collection_filter:
                    continue
                
                content = item.get("content", {})
                metadata = content.get("metadata", {})
                
                # Extract token ID from name if present (e.g., "Genesis LUKi #345")
                token_id = None
                name = metadata.get("name", "")
                if "#" in name:
                    try:
                        token_id = int(name.split("#")[-1].strip())
                    except ValueError:
                        pass
                
                holdings.append(NFTHolding(
                    mint_address=item.get("id", ""),
                    name=name,
                    collection_address=collection_address,
                    token_id=token_id,
                    metadata_uri=content.get("json_uri")
                ))
            
            logger.info(f"Found {len(holdings)} NFTs for wallet {wallet_address[:8]}...")
            return holdings
            
        except Exception as e:
            logger.error(f"Helius NFT query error: {e}")
            return []
    
    async def _get_nfts_basic_rpc(self, wallet_address: str) -> List[NFTHolding]:
        """Fallback: Get NFTs using basic Solana RPC (limited functionality)"""
        try:
            # This is a simplified approach - in production you'd want
            # to use a proper NFT indexer like Helius
            logger.warning("Using basic RPC for NFT query - consider adding Helius API key")
            
            # Get token accounts owned by the wallet
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet_address,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            response = await self.client.post(
                self.solana_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            holdings: List[NFTHolding] = []
            
            accounts = data.get("result", {}).get("value", [])
            for account in accounts:
                parsed = account.get("account", {}).get("data", {}).get("parsed", {})
                info = parsed.get("info", {})
                
                # NFTs have amount = 1 and decimals = 0
                token_amount = info.get("tokenAmount", {})
                if token_amount.get("amount") == "1" and token_amount.get("decimals") == 0:
                    holdings.append(NFTHolding(
                        mint_address=info.get("mint", ""),
                        name=None,  # Would need additional metadata fetch
                        collection_address=None,
                        token_id=None
                    ))
            
            return holdings
            
        except Exception as e:
            logger.error(f"Basic RPC NFT query error: {e}")
            return []
    
    async def get_genesis_personas(self, wallet_address: str) -> List[str]:
        """
        Get list of Genesis persona IDs that a wallet is entitled to.
        
        Args:
            wallet_address: Solana wallet address
            
        Returns:
            List of persona IDs (e.g., ["genesis-1", "genesis-345"])
        """
        if not self.genesis_collection:
            logger.warning("Genesis collection address not configured")
            return []
        
        holdings = await self.get_nft_holdings(
            wallet_address,
            collection_filter=self.genesis_collection
        )
        
        personas: List[str] = []
        for nft in holdings:
            if nft.token_id:
                # NFT names are 1-indexed ("LUKi #595") but persona files are 0-indexed (genesis-594)
                persona_index = nft.token_id - 1
                personas.append(f"genesis-{persona_index}")
        
        return personas
    
    async def get_wallet_entitlements(
        self,
        wallet_address: str
    ) -> WalletEntitlements:
        """
        Get full entitlements for a wallet including personas and avatar assets.
        
        Args:
            wallet_address: Solana wallet address
            
        Returns:
            WalletEntitlements with personas, NFTs, and avatar info
        """
        genesis_nfts = await self.get_nft_holdings(
            wallet_address,
            collection_filter=self.genesis_collection if self.genesis_collection else None
        )
        
        # Filter to only Genesis LUKi NFTs
        if self.genesis_collection:
            genesis_nfts = [
                n for n in genesis_nfts 
                if n.collection_address == self.genesis_collection
            ]
        
        # NFT names are 1-indexed ("LUKi #595") but persona files are 0-indexed (genesis-594)
        personas = [f"genesis-{n.token_id - 1}" for n in genesis_nfts if n.token_id]
        
        # Build avatar assets map
        # In production, these would come from a metadata service
        avatar_assets: Dict[str, str] = {}
        for nft in genesis_nfts:
            if nft.token_id:
                # NFT names are 1-indexed but persona/asset files are 0-indexed
                persona_index = nft.token_id - 1
                persona_id = f"genesis-{persona_index}"
                # Placeholder - would be replaced with actual asset URLs
                avatar_assets[persona_id] = f"/avatars/genesis/{persona_index:04d}.png"
        
        return WalletEntitlements(
            wallet_address=wallet_address,
            genesis_personas=personas,
            genesis_nfts=genesis_nfts,
            default_persona=personas[0] if personas else None,
            avatar_assets=avatar_assets
        )
    
    async def verify_and_get_entitlements(
        self,
        request: WalletVerificationRequest
    ) -> WalletVerificationResponse:
        """
        Verify wallet signature and return entitlements.
        
        This is the main entry point for wallet verification flow.
        
        Args:
            request: WalletVerificationRequest with address, signature, message
            
        Returns:
            WalletVerificationResponse with verification status and personas
        """
        # Verify the signature first
        verified = await self.verify_signature(
            request.wallet_address,
            request.signature,
            request.message
        )
        
        if not verified:
            return WalletVerificationResponse(
                verified=False,
                wallet_address=request.wallet_address,
                genesis_personas=[],
                error="Invalid signature"
            )
        
        # Get Genesis persona entitlements
        personas = await self.get_genesis_personas(request.wallet_address)
        
        logger.info(
            f"Wallet verified: {request.wallet_address[:8]}... "
            f"with {len(personas)} Genesis personas"
        )
        
        return WalletVerificationResponse(
            verified=True,
            wallet_address=request.wallet_address,
            genesis_personas=personas
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Global wallet client instance
wallet_client = WalletClient()
