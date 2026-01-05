from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('menu/', views.menu_view, name='menu'),
    path('about/', views.about_view, name='about'),
    path('contact/', views.contact_view, name='contact'),
    path('cart/', views.cart_view, name='cart'),
    path('checkout/', views.cart_view, name='checkout'),
    path('orders/', views.orders_view, name='orders'),
    path('payment/', views.payment_view, name='payment'),
    path('upi-payment/', views.upi_payment_view, name='upi_payment'),
    path('razorpay/callback/', views.razorpay_callback, name='razorpay_callback'),
    path('razorpay/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('api/submit-contact/', views.submit_contact_form, name='submit_contact'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('bot/', views.chatbot_view, name='chatbot'),  # Chatbot page
   
]
