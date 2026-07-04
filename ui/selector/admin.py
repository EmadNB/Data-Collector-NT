from django.contrib import admin

from .models import Country, Zone


class ZoneInline(admin.TabularInline):
    model = Zone
    extra = 0


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "iso3")
    search_fields = ("name", "iso3")
    inlines = [ZoneInline]


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("code", "country")
    search_fields = ("code", "country__name", "country__iso3")
    list_select_related = ("country",)

