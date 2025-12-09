#!/usr/bin/env python3
"""
Retrieve and display content from IPFS using Pinata gateway
"""
import requests
import json
import base64
import os
import sys
from dotenv import load_dotenv
from PIL import Image
import io

# Load environment variables
load_dotenv()

PINATA_GATEWAY = os.getenv("PINATA_GATEWAY", "amethyst-impossible-ptarmigan-368.mypinata.cloud")
PINATA_API_KEY = os.getenv("PINATA_API_KEY")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY")
PINATA_JWT = os.getenv("PINATA_JWT")

def retrieve_from_ipfs(cid: str):
    """
    Retrieve content from IPFS via Pinata gateway with authentication
    Returns the content as bytes
    """
    # Build list of gateways to try (authenticated first, then public)
    gateways = []
    
    # If we have JWT, try authenticated gateway first
    if PINATA_JWT:
        gateways.append({
            "url": f"https://{PINATA_GATEWAY}/ipfs/{cid}",
            "headers": {
                "Authorization": f"Bearer {PINATA_JWT}"
            },
            "name": "Pinata Authenticated Gateway (JWT)"
        })
    
    # Try public IPFS gateways as fallback
    gateways.extend([
        {"url": f"https://ipfs.io/ipfs/{cid}", "headers": {}, "name": "IPFS.io Public Gateway"},
        {"url": f"https://gateway.pinata.cloud/ipfs/{cid}", "headers": {}, "name": "Pinata Public Gateway"},
        {"url": f"https://dweb.link/ipfs/{cid}", "headers": {}, "name": "Protocol Labs dweb.link"},
        {"url": f"https://{PINATA_GATEWAY}/ipfs/{cid}", "headers": {}, "name": "Custom Pinata Gateway"}
    ])
    
    for i, gateway in enumerate(gateways):
        url = gateway["url"]
        headers = gateway["headers"]
        name = gateway.get("name", "Gateway")
        
        try:
            if i == 0:
                print(f"📥 Retrieving CID: {cid}")
            print(f"   Trying: {name}")
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print(f"   ✅ Success!\n")
                return response.content
            elif response.status_code == 403:
                print(f"   ⚠ 403 Forbidden")
                continue
            elif response.status_code == 404:
                print(f"   ⚠ 404 Not Found")
                continue
            else:
                print(f"   ⚠ Status {response.status_code}")
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"   ⚠ Error: {str(e)[:50]}")
            continue
    
    print(f"❌ Failed to retrieve CID from all gateways")
    print(f"   The content may not be pinned yet, or the CID is invalid")
    return None

def display_image(content: bytes, cid: str):
    """Display image content"""
    try:
        img = Image.open(io.BytesIO(content))
        print(f"✅ Image retrieved successfully!")
        print(f"   Format: {img.format}")
        print(f"   Size: {img.size[0]}x{img.size[1]} pixels")
        print(f"   Mode: {img.mode}")
        
        # Save to file
        filename = f"retrieved_{cid[:10]}.jpg"
        with open(filename, 'wb') as f:
            f.write(content)
        print(f"   Saved to: {filename}\n")
        
        # Try to display (if running in environment that supports it)
        try:
            img.show()
        except:
            print(f"   (Image display not available in this environment)")
        
    except Exception as e:
        print(f"❌ Error processing image: {e}")
        # Save raw bytes anyway
        filename = f"retrieved_{cid[:10]}.bin"
        with open(filename, 'wb') as f:
            f.write(content)
        print(f"   Saved raw content to: {filename}\n")

def display_json(content: bytes, cid: str):
    """Display JSON content"""
    try:
        # Try to decode as JSON
        text = content.decode('utf-8')
        data = json.loads(text)
        
        print(f"✅ JSON retrieved successfully!")
        print(f"   Size: {len(content)} bytes")
        print(f"\n📄 JSON Content:\n")
        print(json.dumps(data, indent=2))
        
        # Save to file
        filename = f"retrieved_{cid[:10]}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"\n   Saved to: {filename}\n")
        
        # If it contains base64 images, try to extract them
        if 'data' in data:
            data_obj = data.get('data', {})
            if 'baseImage' in data_obj:
                print(f"   Contains base64 baseImage (length: {len(data_obj['baseImage'])} chars)")
            if 'depthImage' in data_obj:
                print(f"   Contains base64 depthImage (length: {len(data_obj.get('depthImage', ''))} chars)")
            if 'depthData' in data_obj:
                depth_data = data_obj.get('depthData', {})
                print(f"   Contains depthData:")
                print(f"     - Shape: {depth_data.get('shape', 'N/A')}")
                print(f"     - Valid pixels: {depth_data.get('valid_pixels', 'N/A')}")
            if 'signature' in data:
                sig = data.get('signature', '')
                print(f"   Signature: {sig[:30]}...{sig[-30:] if len(sig) > 60 else ''}")
        
    except json.JSONDecodeError:
        print(f"⚠ Content is not valid JSON")
        print(f"   First 500 characters:")
        print(content[:500].decode('utf-8', errors='ignore'))
        # Save raw content
        filename = f"retrieved_{cid[:10]}.txt"
        with open(filename, 'wb') as f:
            f.write(content)
        print(f"\n   Saved raw content to: {filename}\n")
    except Exception as e:
        print(f"❌ Error processing JSON: {e}")
        filename = f"retrieved_{cid[:10]}.bin"
        with open(filename, 'wb') as f:
            f.write(content)
        print(f"   Saved raw content to: {filename}\n")

def main():
    # Test CIDs from user
    image_cid = "bafkreifuoydyklral6zubbjrirvvu5jdxr6dypemkppzxamnoxfwwja7lu"
    metadata_cid = "bafybeicozdjmw4t3h7ryknzkfxe2v4anh7ablo4tvhrqvcuxqpx63g4e6u"
    
    # Allow command line arguments
    if len(sys.argv) > 1:
        cids = sys.argv[1:]
    else:
        cids = [image_cid, metadata_cid]
    
    print("="*70)
    print("IPFS Content Retriever")
    print("="*70)
    print(f"Gateway: {PINATA_GATEWAY}")
    if PINATA_API_KEY:
        print(f"Using Pinata API authentication")
    print()
    
    for cid in cids:
        print("\n" + "="*70)
        content = retrieve_from_ipfs(cid)
        
        if content is None:
            continue
        
        # Try to determine content type
        # Check if it's an image (JPEG, PNG, etc.)
        if content.startswith(b'\xff\xd8\xff'):  # JPEG
            print(f"📷 Detected: JPEG Image")
            display_image(content, cid)
        elif content.startswith(b'\x89PNG'):  # PNG
            print(f"📷 Detected: PNG Image")
            display_image(content, cid)
        elif content.startswith(b'{') or content.startswith(b'['):  # Likely JSON
            print(f"📄 Detected: JSON")
            display_json(content, cid)
        else:
            # Try JSON first
            try:
                text = content.decode('utf-8')
                json.loads(text)
                print(f"📄 Detected: JSON")
                display_json(content, cid)
            except:
                # Try image
                try:
                    img = Image.open(io.BytesIO(content))
                    print(f"📷 Detected: Image ({img.format})")
                    display_image(content, cid)
                except:
                    print(f"⚠ Unknown content type")
                    print(f"   Size: {len(content)} bytes")
                    print(f"   First 200 bytes (hex): {content[:200].hex()}")
                    print(f"   First 200 bytes (text): {content[:200].decode('utf-8', errors='ignore')}")
                    filename = f"retrieved_{cid[:10]}.bin"
                    with open(filename, 'wb') as f:
                        f.write(content)
                    print(f"   Saved to: {filename}\n")
    
    print("="*70)
    print("✅ Retrieval complete!")

if __name__ == '__main__':
    main()

