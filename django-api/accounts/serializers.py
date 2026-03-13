from django.contrib.auth.models import User
from rest_framework import serializers

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    
    password2 = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']
        
    def validate(self, data):
        
        if data['password'] != data['password2']:
            raise serializers.ValidationError({
                "password": "Passwords do not match."
            })
            
        return data
        
    def create(self, validated_data):
        
        validated_data.pop('password2')
        
        user = User.objects.create_user(username=validated_data['username'],
                                        email=validated_data.get('email', ''),
                                        password=validated_data['password']
                                        )
        
        return user
    
    