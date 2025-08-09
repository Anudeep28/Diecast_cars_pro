from django.contrib import admin
from .models import DiecastCar, CarMarketLink, MarketPrice

@admin.register(DiecastCar)
class DiecastCarAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'manufacturer', 'user', 'price', 'purchase_date', 'delivery_due_date', 'status')
    list_filter = ('status', 'manufacturer')
    search_fields = ('model_name', 'manufacturer', 'user__username')
    readonly_fields = ('purchase_date',)
    
    fieldsets = (
        ('Car Information', {
            'fields': ('user', 'model_name', 'manufacturer', 'price')
        }),
        ('Purchase Details', {
            'fields': ('purchase_date', 'seller_info', 'delivery_due_date', 'status')
        }),
        ('Feedback', {
            'fields': ('packaging_quality', 'product_quality', 'feedback_notes')
        }),
    )


class CarMarketLinkInline(admin.TabularInline):
    model = CarMarketLink
    extra = 0


class MarketPriceInline(admin.TabularInline):
    model = MarketPrice
    extra = 0
    readonly_fields = ('fetched_at',)


# Re-register DiecastCar admin to include inlines
admin.site.unregister(DiecastCar)

@admin.register(DiecastCar)
class DiecastCarAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'manufacturer', 'user', 'price', 'purchase_date', 'delivery_due_date', 'status')
    list_filter = ('status', 'manufacturer')
    search_fields = ('model_name', 'manufacturer', 'user__username')
    readonly_fields = ('purchase_date',)
    inlines = [CarMarketLinkInline, MarketPriceInline]
    
    fieldsets = (
        ('Car Information', {
            'fields': ('user', 'model_name', 'manufacturer', 'scale', 'image', 'price', 'shipping_cost', 'advance_payment', 'remaining_payment')
        }),
        ('Seller & Delivery', {
            'fields': ('seller_name', 'seller_info', 'contact_mobile', 'website_url', 'facebook_page', 'tracking_id', 'delivery_service')
        }),
        ('Dates & Status', {
            'fields': ('purchase_date', 'delivery_due_date', 'delivered_date', 'status')
        }),
        ('Feedback', {
            'fields': ('packaging_quality', 'product_quality', 'feedback_notes')
        }),
    )


@admin.register(CarMarketLink)
class CarMarketLinkAdmin(admin.ModelAdmin):
    list_display = ('car', 'marketplace', 'external_id', 'url', 'updated_at')
    list_filter = ('marketplace',)
    search_fields = ('car__model_name', 'car__manufacturer', 'external_id')


@admin.register(MarketPrice)
class MarketPriceAdmin(admin.ModelAdmin):
    list_display = ('car', 'marketplace', 'price', 'currency', 'fetched_at')
    list_filter = ('marketplace', 'currency')
    search_fields = ('car__model_name', 'car__manufacturer')
