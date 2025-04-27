from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from dependencies import get_current_user, get_profile_by_id
import uuid
import math
import enum


# Models for friend-related routes
class FriendshipStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FriendRequest(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    status: FriendshipStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    sender_profile: Optional[CoreProfile] = None


class Friend(BaseModel):
    id: str
    user_id: str
    friendship_id: str
    created_at: datetime
    profile: Optional[CoreProfile] = None
    distance: Optional[float] = None
    last_active: Optional[datetime] = None


# Create router
router = APIRouter(
    tags=["friends"]
)


@router.post("/request")
async def send_friend_request(
    request: Request,
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Send a friend request to another user"""
    receiver_id = data.get("receiverId")
    if not receiver_id:
        raise HTTPException(status_code=400, detail="Receiver ID is required")
    
    # Check if users are the same
    if current_user["userId"] == receiver_id:
        raise HTTPException(status_code=400, detail="Cannot send friend request to yourself")
    
    # Check if receiver exists
    try:
        receiver_profile = await get_profile_by_id(receiver_id, request.app.state.db_pool)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"User not found: {str(e)}")
    
    # Check if a request already exists or they're already friends
    async with request.app.state.db_pool.acquire() as conn:
        # Check for existing request
        existing_request = await conn.fetchrow('''
            SELECT * FROM friendship_requests 
            WHERE (sender_id = $1 AND receiver_id = $2) OR (sender_id = $2 AND receiver_id = $1)
            AND status = 'pending'
        ''', current_user["userId"], receiver_id)
        
        if existing_request:
            raise HTTPException(status_code=400, detail="A pending friend request already exists between these users")
        
        # Check if already friends
        existing_friendship = await conn.fetchrow('''
            SELECT * FROM friendships 
            WHERE (user1_id = $1 AND user2_id = $2) OR (user1_id = $2 AND user2_id = $1)
        ''', current_user["userId"], receiver_id)
        
        if existing_friendship:
            raise HTTPException(status_code=400, detail="These users are already friends")
        
        # Create new friend request
        request_id = str(uuid.uuid4())
        await conn.execute('''
            INSERT INTO friendship_requests (request_id, sender_id, receiver_id, status, created_at)
            VALUES ($1, $2, $3, $4, $5)
        ''', request_id, current_user["userId"], receiver_id, 'pending', datetime.utcnow())
        
        # Get sender profile to return
        current_user_profile = await get_profile_by_id(current_user["userId"], request.app.state.db_pool)
        
        # Prepare response
        response = {
            "id": request_id,
            "senderId": current_user["userId"],
            "receiverId": receiver_id,
            "status": "pending",
            "createdAt": datetime.utcnow(),
            "senderProfile": {
                "userId": current_user["userId"],
                "username": current_user_profile.get("username"),
                "name": current_user_profile.get("name"),
                "avatarURL": current_user_profile.get("avatar")
            }
        }
        
        return response


@router.post("/accept")
async def accept_friend_request(
    request: Request,
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Accept a friend request"""
    request_id = data.get("requestId")
    if not request_id:
        raise HTTPException(status_code=400, detail="Request ID is required")
    
    async with request.app.state.db_pool.acquire() as conn:
        # Find the request
        friend_request = await conn.fetchrow('''
            SELECT * FROM friendship_requests
            WHERE request_id = $1 AND receiver_id = $2 AND status = 'pending'
        ''', request_id, current_user["userId"])
        
        if not friend_request:
            raise HTTPException(status_code=404, detail="Friend request not found or you're not authorized to accept it")
        
        # Update request status
        await conn.execute('''
            UPDATE friendship_requests
            SET status = 'accepted', updated_at = $1
            WHERE request_id = $2
        ''', datetime.utcnow(), request_id)
        
        # Create friendship record
        friendship_id = str(uuid.uuid4())
        await conn.execute('''
            INSERT INTO friendships (friendship_id, user1_id, user2_id, created_at)
            VALUES ($1, $2, $3, $4)
        ''', friendship_id, friend_request["sender_id"], friend_request["receiver_id"], datetime.utcnow())
        
        # Get friend's profile
        friend_profile = await get_profile_by_id(friend_request["sender_id"], request.app.state.db_pool)
        
        # Get friend's location if available
        friend_location = await conn.fetchrow('''
            SELECT * FROM user_locations
            WHERE user_id = $1 AND visibility != 'hidden'
        ''', friend_request["sender_id"])
        
        response = {
            "id": friendship_id,
            "userId": friend_request["sender_id"],
            "friendshipId": friendship_id,
            "createdAt": datetime.utcnow(),
            "profile": {
                "userId": friend_request["sender_id"],
                "username": friend_profile.get("username"),
                "name": friend_profile.get("name"),
                "avatarURL": friend_profile.get("avatar")
            }
        }
        
        # Add last active time if available
        if friend_location:
            response["lastActive"] = friend_location["timestamp"]
        
        return response


@router.post("/reject")
async def reject_friend_request(
    request: Request,
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Reject a friend request"""
    request_id = data.get("requestId")
    if not request_id:
        raise HTTPException(status_code=400, detail="Request ID is required")
    
    async with request.app.state.db_pool.acquire() as conn:
        # Find the request
        friend_request = await conn.fetchrow('''
            SELECT * FROM friendship_requests
            WHERE request_id = $1 AND receiver_id = $2 AND status = 'pending'
        ''', request_id, current_user["userId"])
        
        if not friend_request:
            raise HTTPException(status_code=404, detail="Friend request not found or you're not authorized to reject it")
        
        # Update request status
        await conn.execute('''
            UPDATE friendship_requests
            SET status = 'rejected', updated_at = $1
            WHERE request_id = $2
        ''', datetime.utcnow(), request_id)
        
        return {"success": True}


@router.post("/remove")
async def remove_friend(
    request: Request,
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Remove a friend"""
    friend_id = data.get("friendId")
    if not friend_id:
        raise HTTPException(status_code=400, detail="Friend ID is required")
    
    async with request.app.state.db_pool.acquire() as conn:
        # Find the friendship
        friendship = await conn.fetchrow('''
            SELECT * FROM friendships
            WHERE friendship_id = $1 AND (user1_id = $2 OR user2_id = $2)
        ''', friend_id, current_user["userId"])
        
        if not friendship:
            raise HTTPException(status_code=404, detail="Friendship not found or you're not authorized to remove it")
        
        # Delete the friendship
        await conn.execute('''
            DELETE FROM friendships
            WHERE friendship_id = $1
        ''', friend_id)
        
        return {"success": True}


@router.get("")
async def get_friends(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get all friends for the current user"""
    async with request.app.state.db_pool.acquire() as conn:
        # Get all friendships for the user
        friendships = await conn.fetch('''
            SELECT * FROM friendships
            WHERE user1_id = $1 OR user2_id = $1
        ''', current_user["userId"])
        
        # Get current user's location if available
        current_user_location = await conn.fetchrow('''
            SELECT * FROM user_locations
            WHERE user_id = $1
        ''', current_user["userId"])
        
        # Decrypt current user's location
        current_user_coords = None
        if current_user_location:
            # For demonstration, we'll use placeholder values
            # In a real implementation, you would decrypt the encrypted_data field
            current_user_coords = {"latitude": 37.7749, "longitude": -122.4194}
        
        friends_list = []
        for friendship in friendships:
            # Determine which user is the friend
            friend_id = friendship["user2_id"] if friendship["user1_id"] == current_user["userId"] else friendship["user1_id"]
            
            # Get friend's profile
            friend_profile = await get_profile_by_id(friend_id, request.app.state.db_pool)
            
            # Get friend's location if available and visible
            friend_location = await conn.fetchrow('''
                SELECT * FROM user_locations
                WHERE user_id = $1 AND visibility != 'hidden'
            ''', friend_id)
            
            # Initialize friend data
            friend = {
                "id": friendship["friendship_id"],
                "userId": friend_id,
                "friendshipId": friendship["friendship_id"],
                "createdAt": friendship["created_at"],
                "profile": {
                    "userId": friend_id,
                    "username": friend_profile.get("username"),
                    "name": friend_profile.get("name"), 
                    "avatarURL": friend_profile.get("avatar")
                }
            }
            
            # Add last active time if available
            if friend_location:
                friend["lastActive"] = friend_location["timestamp"]
            
            # Calculate distance if both locations are available
            if current_user_coords and friend_location:
                # Decrypt friend's location
                # For demonstration, we'll use placeholder values
                # In a real implementation, you would decrypt the encrypted_data field
                friend_coords = {"latitude": 37.7833, "longitude": -122.4167}
                
                distance = calculate_distance(
                    current_user_coords["latitude"], current_user_coords["longitude"],
                    friend_coords["latitude"], friend_coords["longitude"]
                )
                
                friend["distance"] = distance
            
            friends_list.append(friend)
        
        # Sort by distance (closest first)
        friends_list.sort(key=lambda x: x.get("distance", float('inf')))
        
        return friends_list


@router.get("/requests")
async def get_friend_requests(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get pending friend requests for the current user"""
    async with request.app.state.db_pool.acquire() as conn:
        # Get pending requests where current user is the receiver
        requests = await conn.fetch('''
            SELECT * FROM friendship_requests
            WHERE receiver_id = $1 AND status = 'pending'
        ''', current_user["userId"])
        
        result = []
        for req in requests:
            # Get sender profile
            sender_profile = await get_profile_by_id(req["sender_id"], request.app.state.db_pool)
            
            request_data = {
                "id": req["request_id"],
                "senderId": req["sender_id"],
                "receiverId": req["receiver_id"],
                "status": req["status"],
                "createdAt": req["created_at"],
                "updatedAt": req["updated_at"],
                "senderProfile": {
                    "userId": req["sender_id"],
                    "username": sender_profile.get("username"),
                    "name": sender_profile.get("name"),
                    "avatarURL": sender_profile.get("avatar")
                }
            }
            
            result.append(request_data)
        
        return result


# Helper function to calculate distance between two points
def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth specified in decimal degrees
    """
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 3956  # Radius of earth in miles
    
    return c * r