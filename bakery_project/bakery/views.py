from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Prefetch
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from .models import MenuItem, Order, OrderItem, Payment, UserProfile
import json
import uuid
import razorpay
from django.utils import timezone
from decimal import Decimal
import boto3
import os
from botocore.exceptions import ClientError
from datetime import datetime



def process_cart_items(cart_data):
    """Process cart data and return valid order items with total amount"""
    cart = json.loads(cart_data)
    if not cart:
        return None, None, "Cart is empty"
    
    total_amount = Decimal('0.00')
    order_items = []
    
    for item_id, item_data in cart.items():
        try:
            menu_item = MenuItem.objects.get(id=int(item_id))
            quantity = int(item_data.get('quantity', 0))
            if quantity > 0:
                subtotal = menu_item.price * quantity
                total_amount += subtotal
                order_items.append({
                    'menu_item': menu_item,
                    'quantity': quantity,
                    'price': menu_item.price
                })
        except (MenuItem.DoesNotExist, ValueError):
            continue
    
    if not order_items:
        return None, None, "No valid items in cart"
    
    return order_items, total_amount, None


# Simple template views
def index(request):
    return render(request, 'bakery/index.html')


def chatbot_view(request):
    """Display the chatbot interface"""
    return render(request, 'bakery/chatbot_test.html')


def menu_view(request):
    menu_items = MenuItem.objects.filter(available=True)
    return render(request, 'bakery/menu.html', {'menu_items': menu_items})


def about_view(request):
    return render(request, 'bakery/about.html')


def contact_view(request):
    return render(request, 'bakery/contact.html')



@login_required
def cart_view(request):
    return render(request, 'bakery/cart.html')


@login_required
def orders_view(request):
    """Display user-specific orders - only orders belonging to the logged-in user"""
    # Optimized query with prefetch to reduce database hits
    orders_queryset = Order.objects.filter(user=request.user).select_related(
        'payment'
    ).prefetch_related(
        'items__menu_item'
    ).order_by('-created_at')
    
    # Get current active orders
    current_orders = orders_queryset.filter(status__in=['pending', 'confirmed', 'preparing', 'ready'])
    
    # Get order history
    order_history = orders_queryset.filter(status__in=['delivered', 'cancelled'])
    
    # Calculate statistics
    total_orders = orders_queryset.count()
    delivered_orders = orders_queryset.filter(status='delivered').count()
    
    context = {
        'current_orders': current_orders,
        'order_history': order_history,
        'total_orders': total_orders,
        'delivered_orders': delivered_orders,
        'user_full_name': request.user.get_full_name() or request.user.username
    }
    return render(request, 'bakery/orders.html', context)


@login_required
def upi_payment_view(request):
    if request.method != 'POST':
        return render(request, 'bakery/upi-payment.html')
    
    # Get POST data
    cart_data = request.POST.get('cart_data')
    delivery_address = request.POST.get('delivery_address')
    delivery_phone = request.POST.get('delivery_phone')
    delivery_notes = request.POST.get('delivery_notes', '')
    payment_screenshot = request.FILES.get('payment_screenshot')
    upi_transaction_id = request.POST.get('upi_transaction_id', '')
    
    # Validate required fields
    if not all([cart_data, delivery_address, payment_screenshot]):
        messages.error(request, 'Please fill all required fields and upload payment screenshot.')
        return render(request, 'bakery/upi-payment.html')
    
    try:
        # Process cart items
        order_items, total_amount, error = process_cart_items(cart_data)
        if error:
            messages.error(request, error)
            return redirect('cart')
        
        # Create order
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order = Order.objects.create(
            user=request.user,
            order_id=order_id,
            status='pending',
            total_amount=total_amount,
            delivery_address=delivery_address,
            delivery_phone=delivery_phone,
            delivery_notes=delivery_notes
        )
        
        # Create order items
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                menu_item=item['menu_item'],
                quantity=item['quantity'],
                price=item['price']
            ) for item in order_items
        ])
        
        # Create payment record
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        Payment.objects.create(
            order=order,
            payment_method='upi',
            payment_status='pending',
            transaction_id=transaction_id,
            amount=order.grand_total,
            upi_id=upi_transaction_id,
            payment_screenshot=payment_screenshot
        )
        
        # Send order notifications (Email + SMS)
        print(f"📦 Sending notifications for Order #{order.id}...")
        send_order_notification_email(order)
        send_order_sms_notification(order)
        
        success_message = f'Order placed successfully! Order ID: {order_id}. Your payment will be verified within 24 hours.'
        messages.success(request, success_message)
        
        return render(request, 'bakery/upi-payment.html', {
            'order_placed': True,
            'order_id': order_id,
            'message': success_message
        })
        
    except json.JSONDecodeError:
        messages.error(request, 'Invalid cart data.')
    except Exception as e:
        messages.error(request, f'Error processing order: {str(e)}')
    
    return render(request, 'bakery/upi-payment.html')


# Authentication views
def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        
        if user:
            login(request, user)
            messages.success(request, 'Login successful!')
            return redirect(request.GET.get('next', 'index'))
        else:
            messages.error(request, 'Invalid email or password')
    
    return render(request, 'bakery/login.html')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        fullname = request.POST.get('fullname', '')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if User.objects.filter(username=email).exists():
            messages.error(request, 'Email already registered')
            return render(request, 'bakery/signin.html')
        
        # Parse fullname
        name_parts = fullname.split() if fullname else []
        first_name = name_parts[0] if name_parts else ''
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        
        # Create user
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        login(request, user)
        messages.success(request, 'Account created successfully!')
        return redirect('index')
    
    return render(request, 'bakery/signin.html')


def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('index')


# Razorpay Integration - Initialize client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@login_required
def payment_view(request):
    if request.method == 'POST':
        cart_data = request.POST.get('cart_data')
        delivery_address = request.POST.get('delivery_address')
        delivery_phone = request.POST.get('delivery_phone')
        delivery_notes = request.POST.get('delivery_notes', '')
        
        # DEBUG LOGGING
        print("\n=== PAYMENT VIEW DEBUG ===")
        print(f"Cart Data: {cart_data[:100] if cart_data else 'NONE'}")
        print(f"Delivery Address: {delivery_address}")
        print(f"Delivery Phone: {delivery_phone}")
        print(f"Delivery Notes: {delivery_notes}")
        
        # Validate
        if not all([cart_data, delivery_address, delivery_phone]):
            print("❌ VALIDATION FAILED - Missing required fields")
            print(f"cart_data: {bool(cart_data)}, address: {bool(delivery_address)}, phone: {bool(delivery_phone)}")
            messages.error(request, 'Please fill all required fields.')
            return redirect('cart')
        
        try:
            # Process cart
            print("Processing cart items...")
            order_items, total_amount, error = process_cart_items(cart_data)
            if error:
                print(f"❌ CART PROCESSING ERROR: {error}")
                messages.error(request, error)
                return redirect('cart')
            
            print(f"✅ Cart processed: {len(order_items)} items, Total: {total_amount}")
            
            # Create order in database
            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            order = Order.objects.create(
                user=request.user,
                order_id=order_id,
                status='pending',
                total_amount=total_amount,
                delivery_address=delivery_address,
                delivery_phone=delivery_phone,
                delivery_notes=delivery_notes
            )
            
            # Create order items
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    menu_item=item['menu_item'],
                    quantity=item['quantity'],
                    price=item['price']
                ) for item in order_items
            ])
            
            # Create Razorpay order (amount in paise: ₹100 = 10000 paise)
            from decimal import Decimal
            grand_total = Decimal(str(order.total_amount)) + Decimal(str(order.delivery_fee))
            razorpay_amount = int(float(grand_total) * 100)
            print(f"Grand Total: {grand_total}, Razorpay Amount (paise): {razorpay_amount}")
            
            razorpay_order = razorpay_client.order.create({
                'amount': razorpay_amount,
                'currency': 'INR',
                'receipt': order_id,
                'payment_capture': '1'  # Auto capture
            })
            
            # Store Razorpay order ID
            order.razorpay_order_id = razorpay_order['id']
            order.save()
            
            context = {
                'order': order,
                'razorpay_order_id': razorpay_order['id'],
                'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                'amount': razorpay_amount,
                'currency': 'INR',
                'user_name': request.user.get_full_name() or request.user.username,
                'user_email': request.user.email,
                'user_phone': delivery_phone
            }
            print(f"✅ RENDERING RAZORPAY PAYMENT PAGE")
            print(f"   Order ID: {order.order_id}")
            print(f"   Razorpay Order ID: {razorpay_order['id']}")
            print(f"   Amount: {razorpay_amount} paise")
            print("=== END DEBUG ===\n")
            return render(request, 'bakery/razorpay-payment.html', context)
            
        except Exception as e:
            print(f"❌ EXCEPTION IN PAYMENT VIEW: {str(e)}")
            import traceback
            print(traceback.format_exc())
            print("=== END DEBUG ===\n")
            messages.error(request, f'Error creating order: {str(e)}')
            return redirect('cart')
    
    return render(request, 'bakery/payment.html')


@csrf_exempt
@login_required
def razorpay_callback(request):
    """Handle Razorpay payment verification"""
    if request.method == 'POST':
        try:
            # Get payment details
            payment_id = request.POST.get('razorpay_payment_id')
            order_id = request.POST.get('razorpay_order_id')
            signature = request.POST.get('razorpay_signature')
            
            # Verify signature
            params_dict = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            
            try:
                razorpay_client.utility.verify_payment_signature(params_dict)
                
                # Payment verified successfully
                order = Order.objects.get(razorpay_order_id=order_id)
                order.status = 'confirmed'
                order.save()
                
                # Create payment record
                Payment.objects.create(
                    order=order,
                    payment_method='razorpay',
                    payment_status='completed',
                    transaction_id=payment_id,
                    amount=order.grand_total
                )
                
                # Send order notifications (Email + SMS) after successful payment
                print(f"💳 Payment verified! Sending notifications for Order #{order.id}...")
                send_order_notification_email(order)
                send_order_sms_notification(order)
                
                messages.success(request, f'Payment successful! Order ID: {order.order_id}')
                return redirect('orders')
                
            except razorpay.errors.SignatureVerificationError:
                # Payment verification failed
                order = Order.objects.get(razorpay_order_id=order_id)
                order.status = 'cancelled'
                order.save()
                
                Payment.objects.create(
                    order=order,
                    payment_method='razorpay',
                    payment_status='failed',
                    transaction_id=payment_id,
                    amount=order.grand_total
                )
                
                messages.error(request, 'Payment verification failed! Order cancelled.')
                return redirect('cart')
                
        except Exception as e:
            messages.error(request, f'Payment error: {str(e)}')
            return redirect('cart')
    
    return redirect('index')


@csrf_exempt
def razorpay_webhook(request):
    """Handle Razorpay webhooks for automatic confirmation"""
    if request.method == 'POST':
        try:
            # Get webhook secret from environment (set in Razorpay dashboard)
            webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', settings.RAZORPAY_KEY_SECRET)
            webhook_signature = request.headers.get('X-Razorpay-Signature')
            webhook_body = request.body
            
            # Verify webhook signature
            razorpay_client.utility.verify_webhook_signature(
                webhook_body.decode('utf-8'),
                webhook_signature,
                webhook_secret
            )
            
            # Process webhook event
            event_data = json.loads(webhook_body)
            event = event_data.get('event')
            
            if event == 'payment.captured':
                # Payment successful
                payment_entity = event_data['payload']['payment']['entity']
                order_id = payment_entity['notes'].get('order_id')
                
                if order_id:
                    order = Order.objects.get(razorpay_order_id=order_id)
                    order.status = 'confirmed'
                    order.save()
            
            elif event == 'payment.failed':
                # Payment failed
                payment_entity = event_data['payload']['payment']['entity']
                order_id = payment_entity['notes'].get('order_id')
                
                if order_id:
                    order = Order.objects.get(razorpay_order_id=order_id)
                    order.status = 'cancelled'
                    order.save()
            
            return JsonResponse({'status': 'ok'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'status': 'invalid method'}, status=405)


def send_sms_notification(contact_id, name, email, phone, message):
    """Send SMS notification using AWS SNS"""
    try:
        if not settings.SMS_NOTIFICATIONS_ENABLED:
            print("📱 SMS notifications disabled in settings")
            return False
            
        # Create SNS client
        sns = boto3.client(
            'sns',
            region_name=settings.AWS_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        
        # Format SMS message
        sms_message = f"""🍰 NEW CONTACT - {settings.BAKERY_NAME}

Name: {name}
Email: {email}
Phone: {phone if phone else 'Not provided'}
Time: {datetime.now().strftime('%H:%M %d/%m/%Y')}

Message: {message[:100]}{'...' if len(message) > 100 else ''}

Contact ID: {contact_id[:8]}

Reply to: {email}"""
        
        # Send SMS
        response = sns.publish(
            PhoneNumber=settings.ADMIN_PHONE_NUMBER,
            Message=sms_message
        )
        
        print(f"✅ SMS notification sent successfully!")
        print(f"📱 Message ID: {response['MessageId']}")
        print(f"📞 Sent to: {settings.ADMIN_PHONE_NUMBER}")
        
        return True
        
    except Exception as e:
        print(f"❌ SMS notification failed: {str(e)}")
        return False


def send_email_notification(contact_id, name, email, phone, message):
    """Send email notification for contact form submission"""
    try:
        if not settings.EMAIL_NOTIFICATIONS_ENABLED:
            print("📧 Email notifications disabled in settings")
            return False
            
        # Prepare email content
        subject = f'🍰 New Contact Form - {settings.BAKERY_NAME}'
        
        email_message = f"""
New contact form submission received!

📋 CONTACT DETAILS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 Name: {name}
📧 Email: {email}
📱 Phone: {phone if phone else 'Not provided'}
🕒 Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🆔 Contact ID: {contact_id}

💬 MESSAGE:
{message}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 QUICK ACTIONS:
• Reply to customer: {email}
• Call customer: {phone if phone else 'No phone provided'}
• View in admin: http://127.0.0.1:8000/admin/

This notification was sent automatically from {settings.BAKERY_NAME} website.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        
        # Send email
        send_mail(
            subject=subject,
            message=email_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[settings.ADMIN_EMAIL],
            fail_silently=False,
        )
        
        print(f"✅ Email notification sent successfully!")
        print(f"📧 Sent to: {settings.ADMIN_EMAIL}")
        print(f"📋 Subject: {subject}")
        
        return True
        
    except Exception as e:
        print(f"❌ Email notification failed: {str(e)}")
        return False


def send_order_notification_email(order):
    """Send detailed order notification email using AWS SES"""
    try:
        if not settings.ORDER_EMAIL_NOTIFICATIONS_ENABLED:
            print("📧 Order email notifications disabled in settings")
            return False
            
        from django.core.mail import EmailMultiAlternatives
        
        # Get payment status safely
        try:
            payment_status = order.payment.payment_status.upper() if hasattr(order, 'payment') else 'PENDING'
        except:
            payment_status = 'PENDING'
        
        # Calculate order items details
        order_items = order.items.all()
        items_html = ""
        items_text = ""
        
        for item in order_items:
            item_total = item.quantity * item.price
            items_html += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 10px;">{item.menu_item.name}</td>
                    <td style="padding: 10px; text-align: center;">₹{item.price}</td>
                    <td style="padding: 10px; text-align: center;">{item.quantity}</td>
                    <td style="padding: 10px; text-align: right;">₹{item_total}</td>
                </tr>
            """
            items_text += f"• {item.menu_item.name} - ₹{item.price} x {item.quantity} = ₹{item_total}\n"
        
        # Email subject
        subject = f'🍰 NEW ORDER #{order.id} - {settings.BAKERY_BUSINESS_NAME}'
        
        # HTML Email template
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #d2691e; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                .order-details {{ background: white; padding: 15px; margin: 15px 0; border-radius: 8px; border: 1px solid #ddd; }}
                .customer-details {{ background: #e8f4f8; padding: 15px; margin: 15px 0; border-radius: 8px; }}
                .items-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                .items-table th {{ background: #d2691e; color: white; padding: 12px; text-align: left; }}
                .total-row {{ background: #fff2e6; font-weight: bold; }}
                .status {{ padding: 5px 15px; border-radius: 20px; color: white; font-weight: bold; background: #ffc107; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🍰 NEW ORDER RECEIVED!</h1>
                    <h2>Order #{order.id}</h2>
                </div>
                
                <div class="content">
                    <div class="order-details">
                        <h3>📋 Order Information</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Order Date:</strong> {order.created_at.strftime('%d %B %Y at %H:%M')}</p>
                        <p><strong>Status:</strong> <span class="status">{order.status.upper()}</span></p>
                        <p><strong>Payment Status:</strong> {payment_status}</p>
                        <p><strong>Razorpay Order ID:</strong> {order.razorpay_order_id or 'N/A'}</p>
                    </div>
                    
                    <div class="customer-details">
                        <h3>👤 Customer Details</h3>
                        <p><strong>Name:</strong> {order.user.first_name} {order.user.last_name}</p>
                        <p><strong>Email:</strong> {order.user.email}</p>
                        <p><strong>Phone:</strong> {order.delivery_phone}</p>
                        <p><strong>Delivery Address:</strong><br>{order.delivery_address}</p>
                        {f'<p><strong>Special Notes:</strong><br>{order.delivery_notes}</p>' if order.delivery_notes else ''}
                    </div>
                    
                    <div class="order-details">
                        <h3>🛒 Order Items</h3>
                        <table class="items-table">
                            <thead>
                                <tr>
                                    <th>Item</th>
                                    <th style="text-align: center;">Price</th>
                                    <th style="text-align: center;">Quantity</th>
                                    <th style="text-align: right;">Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {items_html}
                                <tr class="total-row">
                                    <td colspan="3" style="padding: 15px; text-align: right;"><strong>Subtotal:</strong></td>
                                    <td style="padding: 15px; text-align: right;"><strong>₹{order.total_amount}</strong></td>
                                </tr>
                                <tr class="total-row">
                                    <td colspan="3" style="padding: 15px; text-align: right;"><strong>Delivery Fee:</strong></td>
                                    <td style="padding: 15px; text-align: right;"><strong>₹{order.delivery_fee}</strong></td>
                                </tr>
                                <tr class="total-row" style="background: #d2691e; color: white;">
                                    <td colspan="3" style="padding: 15px; text-align: right;"><strong>GRAND TOTAL:</strong></td>
                                    <td style="padding: 15px; text-align: right;"><strong>₹{order.grand_total}</strong></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    
                    <div style="text-align: center; margin-top: 30px; padding: 20px; background: #fff; border-radius: 8px;">
                        <h3 style="color: #d2691e;">Next Steps:</h3>
                        <p>1. Confirm the order with the customer</p>
                        <p>2. Prepare the items for delivery/pickup</p>
                        <p>3. Update order status in admin panel</p>
                        <p>4. Send delivery updates to customer</p>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
                    <p>This notification was sent automatically from {settings.BAKERY_BUSINESS_NAME} Order Management System</p>
                    <p>{settings.BAKERY_BUSINESS_ADDRESS} | {settings.BAKERY_BUSINESS_PHONE}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_message = f"""
🍰 NEW ORDER RECEIVED - {settings.BAKERY_BUSINESS_NAME}

ORDER DETAILS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Order ID: #{order.id}
📅 Date: {order.created_at.strftime('%d %B %Y at %H:%M')}
🔄 Status: {order.status.upper()}
💳 Payment: {payment_status}
🔑 Razorpay ID: {order.razorpay_order_id or 'N/A'}

👤 CUSTOMER DETAILS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: {order.user.first_name} {order.user.last_name}
Email: {order.user.email}
Phone: {order.delivery_phone}
Address: {order.delivery_address}
{f'Notes: {order.delivery_notes}' if order.delivery_notes else ''}

🛒 ORDER ITEMS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{items_text}
                                                    
Subtotal: ₹{order.total_amount}
Delivery Fee: ₹{order.delivery_fee}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRAND TOTAL: ₹{order.grand_total}

📝 NEXT STEPS:
1. Confirm order with customer
2. Prepare items for delivery
3. Update order status in admin panel
4. Send delivery updates to customer

📞 Contact Customer: {order.delivery_phone}
📧 Email Customer: {order.user.email}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{settings.BAKERY_BUSINESS_NAME} | {settings.BAKERY_BUSINESS_ADDRESS}
Phone: {settings.BAKERY_BUSINESS_PHONE}
        """
        
        # Send email using AWS SES
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=settings.AWS_SES_FROM_EMAIL,
            to=[settings.ORDER_NOTIFICATION_EMAIL]
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        
        print(f"✅ Order notification email sent via AWS SES for Order #{order.id}")
        print(f"📧 Sent to: {settings.ORDER_NOTIFICATION_EMAIL}")
        print(f"💰 Order Total: ₹{order.grand_total}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to send order notification email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def send_order_sms_notification(order):
    """Send SMS notification for new orders"""
    try:
        if not settings.ORDER_SMS_NOTIFICATIONS_ENABLED:
            print("📱 Order SMS notifications disabled in settings")
            return False
            
        sns = boto3.client(
            'sns',
            region_name=settings.AWS_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        
        # Get payment status safely
        try:
            payment_status = order.payment.payment_status.upper() if hasattr(order, 'payment') else 'PENDING'
        except:
            payment_status = 'PENDING'
        
        # Count items
        item_count = order.items.count()
        
        # Get first few items for SMS
        order_items = order.items.all()[:3]
        items_summary = ", ".join([item.menu_item.name for item in order_items])
        if item_count > 3:
            items_summary += f" +{item_count - 3} more"
        
        sms_message = f"""🍰 NEW ORDER - {settings.BAKERY_BUSINESS_NAME}

Order #{order.id}
Customer: {order.user.first_name} {order.user.last_name}
Amount: ₹{order.grand_total}
Phone: {order.delivery_phone}

Items ({item_count}): {items_summary}

Status: {order.status.upper()}
Payment: {payment_status}

Check email for full details!"""
        
        response = sns.publish(
            PhoneNumber=settings.ADMIN_PHONE_NUMBER,
            Message=sms_message,
            MessageAttributes={{
                'AWS.SNS.SMS.SMSType': {{
                    'DataType': 'String',
                    'StringValue': 'Transactional'
                }}
            }}
        )
        
        print(f"✅ Order SMS sent for Order #{order.id}")
        print(f"📱 Sent to: {settings.ADMIN_PHONE_NUMBER}")
        print(f"📨 Message ID: {response['MessageId']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Order SMS failed: {str(e)}")
        return False


@csrf_exempt
def submit_contact_form(request):
    """Store contact form submissions in AWS DynamoDB and send SMS notification"""
    if request.method == 'POST':
        try:
            # Get form data
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            email = data.get('email', '').strip()
            phone = data.get('phone', '').strip()
            message = data.get('message', '').strip()
            
            # Validate required fields
            if not name or not email or not message:
                return JsonResponse({
                    'success': False,
                    'error': 'Name, email, and message are required'
                }, status=400)
            
            # Initialize DynamoDB client
            dynamodb = boto3.resource(
                'dynamodb',
                region_name=settings.AWS_REGION_NAME,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            
            table = dynamodb.Table(settings.DYNAMODB_CONTACT_TABLE)
            
            # Generate unique contact ID
            contact_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Store in DynamoDB
            item = {
                'contact_id': contact_id,
                'name': name,
                'email': email,
                'phone': phone if phone else 'Not provided',
                'message': message,
                'timestamp': timestamp,
                'status': 'new'  # Can be: new, read, responded
            }
            
            table.put_item(Item=item)
            
            print(f"✅ Contact form submitted - ID: {contact_id}")
            print(f"   Name: {name}, Email: {email}")
            
            # � SEND EMAIL NOTIFICATION (Primary)
            email_sent = send_email_notification(contact_id, name, email, phone, message)
            
            # �📱 SEND SMS NOTIFICATION (Secondary - if enabled)
            sms_sent = False
            if settings.SMS_NOTIFICATIONS_ENABLED:
                sms_sent = send_sms_notification(contact_id, name, email, phone, message)
            
            # Log notification results
            if email_sent:
                print(f"📧 Email alert sent for contact from {name}")
            else:
                print(f"⚠️ Email alert failed for contact from {name}")
                
            if settings.SMS_NOTIFICATIONS_ENABLED:
                if sms_sent:
                    print(f"📱 SMS alert sent for contact from {name}")
                else:
                    print(f"⚠️ SMS alert failed for contact from {name}")
            
            return JsonResponse({
                'success': True,
                'message': 'Thank you for your message! We will get back to you soon.',
                'contact_id': contact_id
            })
            
        except ClientError as e:
            error_msg = f"AWS DynamoDB Error: {str(e)}"
            print(f"❌ DynamoDB Error: {error_msg}")
            return JsonResponse({
                'success': False,
                'error': 'Unable to save your message. Please try again later.'
            }, status=500)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid request data'
            }, status=400)
            
        except Exception as e:
            print(f"❌ Unexpected error in contact form: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'An error occurred. Please try again later.'
            }, status=500)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)