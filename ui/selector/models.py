from django.db import models


class Country(models.Model):
    """
    ISO3 matches the GeoJSON dataset used in the UI (feature.id).
    """

    iso3 = models.CharField(max_length=3, unique=True)
    iso2 = models.CharField(max_length=2, unique=True, null=True, blank=True)
    name = models.CharField(max_length=128)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.iso2 or self.iso3})"


class Zone(models.Model):
    code = models.CharField(max_length=8, unique=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="zones")

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code

