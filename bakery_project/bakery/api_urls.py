from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views 
from .views import upi_payment_view
from . import chatbot_views 

# Create router and register viewsets
router = DefaultRouter()
router.register(r'menu-items', api_views.MenuItemViewSet, basename='menu-item')
router.register(r'orders', api_views.OrderViewSet, basename='order')
router.register(r'payments', api_views.PaymentViewSet, basename='payment')
router.register(r'profiles', api_views.UserProfileViewSet, basename='profile')


# URL patterns
urlpatterns = [
    # Router URLs (includes all CRUD operations for registered viewsets)
    path('', include(router.urls)),
    
    # Authentication endpoints
    path('auth/register/', api_views.register_api, name='api_register'),
    path('auth/login/', api_views.login_api, name='api_login'),
    path('auth/logout/', api_views.logout_api, name='api_logout'),
    path('auth/user/', api_views.current_user_api, name='api_current_user'),
    
    # Dashboard
    path('dashboard/stats/', api_views.dashboard_stats_api, name='api_dashboard_stats'),

    path('dashboard/upi-payments/', upi_payment_view, name='upi-payment'),
    
    # Chatbot endpoints
    path('chatbot/query/', chatbot_views.chatbot_query, name='chatbot_query'),
    path('chatbot/refresh/', chatbot_views.chatbot_refresh, name='chatbot_refresh'),
    path('chatbot/status/', chatbot_views.chatbot_status, name='chatbot_status'),
    
    # Chatbot order flow
    path('chatbot/order/search/', chatbot_views.chatbot_order_search, name='chatbot_order_search'),
    path('chatbot/order/initiate/', chatbot_views.chatbot_order_initiate, name='chatbot_order_initiate'),
    path('chatbot/order/address/', chatbot_views.chatbot_order_address, name='chatbot_order_address'),
    path('chatbot/order/create/', chatbot_views.chatbot_order_create, name='chatbot_order_create'),
    path('chatbot/order/payment/verify/', chatbot_views.chatbot_order_payment_verify, name='chatbot_order_payment_verify'),
    path('chatbot/order/status/<str:order_id>/', chatbot_views.chatbot_order_status, name='chatbot_order_status'),
]
