from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
import json
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Deepshare IPFS Service")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pinata configuration
PINATA_JWT = os.getenv("PINATA_JWT")
PINATA_API_KEY = os.getenv("PINATA_API_KEY")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY")
PINATA_GATEWAY = os.getenv("PINATA_GATEWAY")
PINATA_API_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

# Check for Pinata credentials (either JWT or API Key/Secret)
if not PINATA_JWT and (not PINATA_API_KEY or not PINATA_SECRET_KEY):
    raise ValueError("Pinata credentials not found. Set either PINATA_JWT or PINATA_API_KEY + PINATA_SECRET_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials not found in environment variables")


def upload_to_ipfs(file_data: bytes, filename: str, metadata: dict) -> str:
    """
    Upload file and metadata to IPFS via Pinata
    Returns the IPFS CID
    """
    # Prepare files for Pinata
    files = {
        'file': (filename, file_data, 'application/octet-stream')
    }
    
    # Prepare metadata as JSON
    pinata_metadata = {
        "name": filename,
        "keyvalues": metadata
    }
    
    # Use API Key/Secret if available (more reliable), otherwise use JWT
    if PINATA_API_KEY and PINATA_SECRET_KEY:
        headers = {
            "pinata_api_key": PINATA_API_KEY,
            "pinata_secret_api_key": PINATA_SECRET_KEY
        }
    elif PINATA_JWT:
        headers = {
            "Authorization": f"Bearer {PINATA_JWT}"
        }
    else:
        raise ValueError("No Pinata credentials available")
    
    data = {
        "pinataMetadata": json.dumps(pinata_metadata),
        "pinataOptions": json.dumps({
            "cidVersion": 1
        })
    }
    
    try:
        # Don't set Content-Type header - requests library will set it automatically for multipart/form-data
        # Remove Content-Type if it exists to let requests handle it
        upload_headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}
        
        response = requests.post(
            PINATA_API_URL,
            files=files,
            data=data,
            headers=upload_headers,
            timeout=60
        )
        
        # Better error handling
        if response.status_code != 200:
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = json.dumps(error_json, indent=2)
            except:
                pass
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Pinata API error ({response.status_code}): {error_detail}"
            )
        
        response.raise_for_status()
        
        result = response.json()
        ipfs_hash = result.get("IpfsHash")
        
        if not ipfs_hash:
            raise ValueError("No IPFS hash returned from Pinata")
        
        # Log the CID
        print(f"✅ Pinata upload successful - CID: {ipfs_hash}")
        
        return ipfs_hash
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Pinata upload failed: {str(e)}")


def store_in_supabase(wallet_address: str, image_cid: str, metadata_cid: str):
    """
    Store wallet_address, image_cid, and metadata_cid in Supabase images table using REST API
    """
    try:
        # Try both lowercase and quoted table name (Supabase can be case-sensitive)
        url = f"{SUPABASE_URL}/rest/v1/images"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        data = {
            "wallet_address": wallet_address,
            "image_cid": image_cid,
            "metadata_cid": metadata_cid
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=10)
        
        # If 401, try with quoted table name
        if response.status_code == 401:
            print(f"⚠ First attempt failed with 401, trying with quoted table name...")
            url = f"{SUPABASE_URL}/rest/v1/\"images\""
            response = requests.post(url, json=data, headers=headers, timeout=10)
        
        # Better error handling
        if response.status_code == 401:
            error_msg = "Supabase authentication failed (401 Unauthorized)"
            try:
                error_json = response.json()
                error_msg += f": {error_json.get('message', response.text)}"
            except:
                error_msg += f": Check your SUPABASE_KEY - it may be invalid, expired, or RLS policies are blocking"
            print(f"❌ Supabase error: {error_msg}")
            raise HTTPException(status_code=401, detail=error_msg)
        
        if response.status_code == 404:
            error_msg = "Supabase table 'images' not found. Make sure the table exists and is accessible."
            print(f"❌ Supabase error: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        response.raise_for_status()
        
        result = response.json()
        print(f"✅ Supabase insert successful")
        return result
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        error_detail = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_json = e.response.json()
                error_detail = json.dumps(error_json, indent=2)
            except:
                error_detail = e.response.text
        print(f"❌ Supabase error: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Supabase insert failed: {error_detail}")


@app.get("/")
async def root():
    return {"message": "i-Witness IPFS Service", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/check-registration/{wallet_address}")
async def check_registration(wallet_address: str):
    """
    Check if a device with the given wallet_address is registered in Supabase Devices table
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/Devices"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
        params = {
            "wallet_address": f"eq.{wallet_address}",
            "select": "wallet_address"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        is_registered = len(data) > 0
        
        return JSONResponse(
            status_code=200,
            content={
                "registered": is_registered,
                "wallet_address": wallet_address
            }
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Registration check failed: {str(e)}")


@app.post("/upload")
async def upload_capture(
    wallet_address: str = Form(...),
    image: UploadFile = File(...),
    metadata: str = Form(...)
):
    """
    Upload image and metadata to IPFS, then store CID in Supabase
    
    Parameters:
    - wallet_address: Ethereum wallet address of the device
    - image: The original image file
    - metadata: JSON string containing depth information and other metadata
    """
    try:
        # Read image file
        image_data = await image.read()
        
        # Parse metadata
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in metadata")
        
        # Add wallet address to metadata
        metadata_dict["wallet_address"] = wallet_address
        
        # Upload to IPFS
        filename = image.filename or f"capture_{wallet_address[:10]}.jpg"
        cid = upload_to_ipfs(image_data, filename, metadata_dict)
        
        # Store in Supabase (for /upload endpoint, use same CID for both image and metadata)
        store_in_supabase(wallet_address, cid, cid)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "cid": cid,
                "gateway_url": f"https://{PINATA_GATEWAY}/ipfs/{cid}",
                "wallet_address": wallet_address
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/upload-json")
async def upload_json_capture(
    wallet_address: str = Form(...),
    image: UploadFile = File(...),
    metadata: str = Form(...)
):
    """
    Upload original image and JSON metadata to IPFS, then store CID in Supabase
    
    Parameters:
    - wallet_address: Ethereum wallet address of the device
    - image: The original image file (JPEG)
    - metadata: JSON string containing the full capture data (base64 images, depth data, signature, etc.)
    """
    try:
        # Read image file
        image_data = await image.read()
        
        # Parse and validate metadata JSON
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in metadata")
        
        # Upload original image to IPFS
        timestamp = int(time.time())
        image_filename = f"original_{wallet_address[:10]}_{timestamp}.jpg"
        print(f"📤 Uploading image to Pinata...")
        image_cid = upload_to_ipfs(image_data, image_filename, {
            "wallet_address": wallet_address,
            "type": "original_image"
        })
        print(f"✅ Image uploaded to IPFS - CID: {image_cid}")
        
        # Upload metadata JSON to IPFS (includes depth data, base64 images, signature)
        metadata_dict["wallet_address"] = wallet_address
        metadata_dict["image_cid"] = image_cid  # Link metadata to image
        json_bytes = json.dumps(metadata_dict, separators=(',', ':')).encode('utf-8')
        json_filename = f"metadata_{wallet_address[:10]}_{timestamp}.json"
        print(f"📤 Uploading metadata to Pinata...")
        json_cid = upload_to_ipfs(json_bytes, json_filename, {
            "wallet_address": wallet_address,
            "type": "metadata",
            "image_cid": image_cid
        })
        print(f"✅ Metadata uploaded to IPFS - CID: {json_cid}")
        
        # Store both CIDs in Supabase (wallet_address, image_cid, metadata_cid)
        print(f"📤 Storing CIDs in Supabase...")
        store_in_supabase(wallet_address, image_cid, json_cid)
        print(f"✅ CIDs stored in Supabase - Image: {image_cid}, Metadata: {json_cid}")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "cid": image_cid,
                "metadata_cid": json_cid,
                "gateway_url": f"https://{PINATA_GATEWAY}/ipfs/{image_cid}",
                "wallet_address": wallet_address
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

