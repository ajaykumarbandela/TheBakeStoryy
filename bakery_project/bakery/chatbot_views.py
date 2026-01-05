"""
Django API views for RAG Chatbot
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth.models import User
import os
import json
import razorpay
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv

# Import chatbot and models
from .rag_chatbot import DatabaseRAGChatbot
from .models import MenuItem, Order, OrderItem, Payment
from django.db import models

# Load environment
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

# Initialize chatbot globally (so it persists across requests)
chatbot_instance = None

# Session storage for order flow (in production, use Redis or database)
order_sessions = {}


def get_chatbot():
    """Get or create chatbot instance"""
    global chatbot_instance
    if chatbot_instance is None:
        chatbot_instance = DatabaseRAGChatbot(GROQ_API_KEY)
        chatbot_instance.initialize()
    return chatbot_instance


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_query(request):
    """
    API endpoint to handle chatbot queries
    
    POST /api/chatbot/query/
    Body: {"query": "your question here"}
    """
    try:
        query = request.data.get('query', '')
        
        if not query:
            return Response(
                {"error": "Query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get chatbot and ask question
        chatbot = get_chatbot()
        answer = chatbot.ask(query)
        
        return Response({
            "query": query,
            "answer": answer,
            "status": "success"
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Error in chatbot_query: {error_details}")
        return Response(
            {"error": str(e), "details": error_details, "status": "error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_refresh(request):
    """
    API endpoint to refresh chatbot data from database
    
    POST /api/chatbot/refresh/
    """
    try:
        global chatbot_instance
        chatbot_instance = None  # Reset instance
        chatbot = get_chatbot()  # Reinitialize
        
        return Response({
            "message": "Chatbot data refreshed successfully",
            "status": "success"
        })
        
    except Exception as e:
        return Response(
            {"error": str(e), "status": "error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def chatbot_status(request):
    """
    API endpoint to check chatbot status
    
    GET /api/chatbot/status/
    """
    global chatbot_instance
    return Response({
        "initialized": chatbot_instance is not None,
        "status": "ready" if chatbot_instance is not None else "not initialized"
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_order_search(request):
    """
    Search for menu items by name or category for ordering
    POST /api/chatbot/order/search/
    Body: {"query": "cake" or "ramen"}
    """
    try:
        query = request.data.get('query', '').lower().strip()
        
        # Normalize query by removing extra spaces and special characters
        normalized_query = ''.join(query.split()).lower()
        
        # Search in menu items with multiple strategies
        items = MenuItem.objects.filter(available=True)
        
        # Strategy 1: Exact match (case-insensitive)
        exact_matches = items.filter(name__iexact=query)
        
        # Strategy 2: Contains match (with spaces)
        contains_matches = items.filter(
            models.Q(name__icontains=query) | 
            models.Q(description__icontains=query) |
            models.Q(category__icontains=query)
        )
        
        # Strategy 3: Fuzzy match (remove spaces from both sides)
        fuzzy_matches = []
        if not exact_matches.exists() and not contains_matches.exists():
            for item in items:
                normalized_item_name = ''.join(item.name.split()).lower()
                # Check if normalized query is in normalized item name
                if normalized_query in normalized_item_name or normalized_item_name in normalized_query:
                    fuzzy_matches.append(item)
                # Also check individual words
                elif any(word in normalized_item_name for word in query.split() if len(word) > 2):
                    fuzzy_matches.append(item)
        
        # Combine results (exact first, then contains, then fuzzy)
        if exact_matches.exists():
            final_items = list(exact_matches[:5])
        elif contains_matches.exists():
            final_items = list(contains_matches[:5])
        else:
            final_items = fuzzy_matches[:5]
        
        if not final_items:
            return Response({
                "found": False,
                "message": f"Sorry, we don't have '{query}' on our menu. Would you like to see our available items?",
                "items": []
            })
        
        items_data = [{
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'price': float(item.price),
            'category': item.category,
            'image_url': item.image_url
        } for item in final_items]
        
        return Response({
            "found": True,
            "items": items_data,
            "message": f"Found {len(items_data)} item(s) matching '{query}'"
        })
        
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_order_initiate(request):
    """
    Initiate order process - collect item and quantity
    POST /api/chatbot/order/initiate/
    Body: {"item_id": 1, "quantity": 2, "user_id": 1 (optional)}
    """
    try:
        item_id = request.data.get('item_id')
        quantity = request.data.get('quantity', 1)
        user_id = request.data.get('user_id') or request.user.id if request.user.is_authenticated else None
        
        # Validate item
        try:
            menu_item = MenuItem.objects.get(id=item_id, available=True)
        except MenuItem.DoesNotExist:
            return Response({
                "success": False,
                "message": "This item is not available."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create session ID
        import uuid
        session_id = str(uuid.uuid4())
        
        # Calculate total
        item_total = float(menu_item.price) * int(quantity)
        delivery_fee = 50.00
        grand_total = item_total + delivery_fee
        
        # Store in session
        order_sessions[session_id] = {
            'item_id': item_id,
            'item_name': menu_item.name,
            'quantity': quantity,
            'price': float(menu_item.price),
            'item_total': item_total,
            'delivery_fee': delivery_fee,
            'grand_total': grand_total,
            'user_id': user_id,
            'step': 'collect_address',
            'created_at': datetime.now().isoformat()
        }
        
        return Response({
            "success": True,
            "session_id": session_id,
            "item": {
                'name': menu_item.name,
                'quantity': quantity,
                'price': float(menu_item.price),
                'item_total': item_total,
                'delivery_fee': delivery_fee,
                'grand_total': grand_total
            },
            "next_step": "collect_address",
            "message": f"Great! I'll help you order {quantity}x {menu_item.name} for ₹{grand_total:.2f}. Please provide your delivery address."
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_order_address(request):
    """
    Collect delivery address
    POST /api/chatbot/order/address/
    Body: {"session_id": "...", "address": "...", "phone": "..."}
    """
    try:
        session_id = request.data.get('session_id')
        address = request.data.get('address', '').strip()
        phone = request.data.get('phone', '').strip()
        
        if not session_id or session_id not in order_sessions:
            return Response({
                "success": False,
                "message": "Invalid or expired session. Please start a new order."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not address:
            return Response({
                "success": False,
                "message": "Please provide a valid delivery address."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update session
        order_sessions[session_id]['delivery_address'] = address
        order_sessions[session_id]['delivery_phone'] = phone
        order_sessions[session_id]['step'] = 'confirm_order'
        
        session_data = order_sessions[session_id]
        
        return Response({
            "success": True,
            "session_id": session_id,
            "order_summary": {
                'item_name': session_data['item_name'],
                'quantity': session_data['quantity'],
                'item_total': session_data['item_total'],
                'delivery_fee': session_data['delivery_fee'],
                'grand_total': session_data['grand_total'],
                'delivery_address': address,
                'delivery_phone': phone
            },
            "next_step": "confirm_order",
            "message": "Perfect! Here's your order summary. Ready to proceed with payment?"
        })
        
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_order_create(request):
    """
    Create order and initiate Razorpay payment
    POST /api/chatbot/order/create/
    Body: {"session_id": "..."}
    """
    try:
        session_id = request.data.get('session_id')
        
        if not session_id or session_id not in order_sessions:
            return Response({
                "success": False,
                "message": "Invalid or expired session."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        session_data = order_sessions[session_id]
        
        # Get or create user
        if session_data.get('user_id'):
            user = User.objects.get(id=session_data['user_id'])
        elif request.user.is_authenticated:
            user = request.user
        else:
            # Create guest user
            import uuid
            guest_username = f"guest_{uuid.uuid4().hex[:8]}"
            user = User.objects.create_user(
                username=guest_username,
                email=f"{guest_username}@guest.com"
            )
        
        # Generate order ID
        import random
        order_id = f"ORD{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
        
        # Create Razorpay order
        razorpay_amount = int(session_data['grand_total'] * 100)  # Convert to paise
        razorpay_order = razorpay_client.order.create({
            'amount': razorpay_amount,
            'currency': 'INR',
            'receipt': order_id,
            'payment_capture': 1
        })
        
        # Create Order
        order = Order.objects.create(
            user=user,
            order_id=order_id,
            status='pending',
            total_amount=Decimal(str(session_data['item_total'])),
            delivery_fee=Decimal(str(session_data['delivery_fee'])),
            delivery_address=session_data.get('delivery_address', ''),
            delivery_phone=session_data.get('delivery_phone', ''),
            razorpay_order_id=razorpay_order['id']
        )
        
        # Create OrderItem
        menu_item = MenuItem.objects.get(id=session_data['item_id'])
        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=session_data['quantity'],
            price=Decimal(str(session_data['price']))
        )
        
        # Update session
        order_sessions[session_id]['order_id'] = order_id
        order_sessions[session_id]['razorpay_order_id'] = razorpay_order['id']
        order_sessions[session_id]['db_order_id'] = order.id
        
        return Response({
            "success": True,
            "order_id": order_id,
            "razorpay_order_id": razorpay_order['id'],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount": razorpay_amount,
            "currency": "INR",
            "order_details": {
                'order_id': order_id,
                'item_name': session_data['item_name'],
                'quantity': session_data['quantity'],
                'grand_total': session_data['grand_total'],
                'delivery_address': session_data.get('delivery_address'),
            },
            "message": "Order created! Please complete the payment."
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def chatbot_order_payment_verify(request):
    """
    Verify Razorpay payment and confirm order
    POST /api/chatbot/order/payment/verify/
    Body: {
        "razorpay_order_id": "...",
        "razorpay_payment_id": "...",
        "razorpay_signature": "..."
    }
    """
    try:
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')
        
        # Verify signature
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
        except Exception as verify_error:
            import traceback
            print("Payment verification error:")
            print(traceback.format_exc())
            return Response({
                "success": False,
                "message": "Payment verification failed. Please contact support.",
                "error": str(verify_error)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find order
        order = Order.objects.get(razorpay_order_id=razorpay_order_id)
        
        # Update order status
        order.status = 'confirmed'
        order.confirmed_at = datetime.now()
        order.save()
        
        # Create payment record
        Payment.objects.create(
            order=order,
            payment_method='card',  # or detect from razorpay
            amount=order.grand_total,
            status='completed',
            transaction_id=razorpay_payment_id,
            payment_screenshot=''
        )
        
        return Response({
            "success": True,
            "message": "🎉 Payment successful! Your order has been confirmed and will be delivered soon.",
            "order_id": order.order_id,
            "status": "confirmed",
            "estimated_delivery": "30-45 minutes",
            "order_details": {
                'order_id': order.order_id,
                'status': order.get_status_display(),
                'total': float(order.grand_total),
                'delivery_address': order.delivery_address,
            }
        })
        
    except Order.DoesNotExist:
        return Response({
            "success": False,
            "message": "Order not found."
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def chatbot_order_status(request, order_id):
    """
    Check order status
    GET /api/chatbot/order/status/<order_id>/
    """
    try:
        order = Order.objects.get(order_id=order_id)
        
        return Response({
            "success": True,
            "order": {
                'order_id': order.order_id,
                'status': order.get_status_display(),
                'total': float(order.grand_total),
                'delivery_address': order.delivery_address,
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
                'items': [
                    {
                        'name': item.menu_item.name,
                        'quantity': item.quantity,
                        'price': float(item.price)
                    }
                    for item in order.items.all()
                ]
            }
        })
        
    except Order.DoesNotExist:
        return Response({
            "success": False,
            "message": "Order not found."
        }, status=status.HTTP_404_NOT_FOUND)
