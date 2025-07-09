from django.contrib import admin
from .models import DiecastCar

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
