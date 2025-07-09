from django.urls import path
from django.contrib.auth import views as auth_views

# Import main views
from . import views

# Import fix_subscription_view directly
from .fix_subscription import fix_subscription_view

urlpatterns = [
    # Dashboard and CRUD operations
    path('', views.dashboard, name='dashboard'),
    path('car/new/', views.car_create, name='car_create'),
    path('car/<int:pk>/', views.car_detail, name='car_detail'),
    path('car/<int:pk>/update/', views.car_update, name='car_update'),
    path('car/<int:pk>/delete/', views.car_delete, name='car_delete'),
    path('car/<int:pk>/status/', views.update_status, name='update_status'),
    
    # Authentication URLs
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='inventory/login.html'), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    
    # Subscription and payment URLs
    path('subscription/callback/', views.subscription_callback, name='subscription_callback'),
    path('subscription/success/', views.payment_success, name='payment_success'),
    path('subscription/failed/', views.payment_failed, name='payment_failed'),
    path('subscription/renew/', views.subscription_renew, name='subscription_renew'),
    path('subscription/details/', views.subscription_details, name='subscription_details'),
    path('profile/', views.profile, name='profile'),
    path('subscription/fix/', fix_subscription_view, name='fix_subscription'),
    path('password-reset/', 
        auth_views.PasswordResetView.as_view(template_name='inventory/password_reset.html'), 
        name='password_reset'),
    path('password-reset/done/', 
        auth_views.PasswordResetDoneView.as_view(template_name='inventory/password_reset_done.html'), 
        name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
        auth_views.PasswordResetConfirmView.as_view(template_name='inventory/password_reset_confirm.html'), 
        name='password_reset_confirm'),
    path('password-reset-complete/', 
        auth_views.PasswordResetCompleteView.as_view(template_name='inventory/password_reset_complete.html'), 
        name='password_reset_complete'),
]
