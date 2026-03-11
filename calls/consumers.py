from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from uuid import UUID
import json

from .models import Room, RoomParticipant


class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.group_name = f'call_{self.room_name}'
        self.room_id = await self._resolve_or_create_room_id(self.room_name)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except Exception:
            return

        msg_type = data.get('type')

        await self._register_participant_from_payload(data, increment_join=(msg_type == 'join'))

        if msg_type == 'chat':
            # Only relay name + message; discard any other fields for safety
            payload = {
                'type': 'chat',
                'name': str(data.get('name', 'Anônimo'))[:80],
                'message': str(data.get('message', ''))[:1000],
            }
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'chat.message', 'sender': self.channel_name, 'data': payload},
            )
            return

        if msg_type == 'raise_hand':
            payload = {
                'type': 'hand_raise',
                'client_id': str(data.get('client_id', ''))[:40],
                'name': str(data.get('name', 'Anônimo'))[:80],
            }
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'hand.raise', 'sender': self.channel_name, 'data': payload},
            )
            return

        if msg_type == 'lower_hand':
            payload = {
                'type': 'hand_lower',
                'client_id': str(data.get('client_id', ''))[:40],
            }
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'hand.lower', 'sender': self.channel_name, 'data': payload},
            )
            return

        # Relay all other signaling messages to the room group, include sender to avoid loops
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'signal.message',
                'sender': self.channel_name,
                'data': data,
            }
        )

    async def chat_message(self, event):
        # Don't echo back to the sender (they already rendered the message locally)
        if event.get('sender') == self.channel_name:
            return
        await self.send(text_data=json.dumps(event.get('data')))

    async def hand_raise(self, event):
        # Echo to everyone including sender so all queues stay in sync
        await self.send(text_data=json.dumps(event.get('data')))

    async def hand_lower(self, event):
        await self.send(text_data=json.dumps(event.get('data')))

    async def signal_message(self, event):
        # Don't send message back to originating channel
        if event.get('sender') == self.channel_name:
            return
        await self.send(text_data=json.dumps(event.get('data')))

    async def _register_participant_from_payload(self, payload, increment_join=False):
        client_id = str(payload.get('client_id') or payload.get('from') or '').strip()[:40]
        if not client_id:
            return

        name = str(payload.get('name') or '').strip()[:80]
        roles = payload.get('roles')
        image_url = payload.get('imageUrl')
        if image_url is None:
            image_url = payload.get('image_url')

        await self._upsert_room_participant(
            client_id=client_id,
            name=name,
            roles=roles,
            image_url=str(image_url).strip()[:500] if image_url else '',
            increment_join=increment_join,
        )

    @database_sync_to_async
    def _resolve_or_create_room_id(self, room_identifier):
        value = str(room_identifier or '').strip()
        if not value:
            return None

        try:
            parsed_uuid = UUID(value)
            room, _ = Room.objects.get_or_create(id=parsed_uuid)
            return str(room.id)
        except (ValueError, TypeError, AttributeError):
            room = Room.objects.filter(name__iexact=value).order_by('-created_at').first()
            if room is None:
                room = Room.objects.create(name=value)
            return str(room.id)

    @database_sync_to_async
    def _upsert_room_participant(self, client_id, name='', roles=None, image_url='', increment_join=False):
        room_id = str(getattr(self, 'room_id', '') or '').strip()
        if not room_id:
            return

        room = Room.objects.filter(id=room_id).first()
        if room is None:
            return

        normalized_roles = []
        if isinstance(roles, str):
            roles = [roles]
        if isinstance(roles, list):
            normalized_roles = [str(role).strip() for role in roles if str(role).strip()]

        participant_name = str(name or '').strip()[:80]
        if not participant_name:
            participant_name = f'Participante {client_id[:6]}'

        defaults = {
            'name': participant_name,
            'roles_json': json.dumps(normalized_roles),
            'image_url': str(image_url or '').strip()[:500],
            'join_count': 1,
        }

        participant, created = RoomParticipant.objects.get_or_create(
            room=room,
            client_id=client_id,
            defaults=defaults,
        )

        if created:
            return

        update_fields = ['last_seen_at']
        participant.last_seen_at = timezone.now()

        if increment_join:
            participant.join_count = int(participant.join_count or 0) + 1
            update_fields.append('join_count')

        if participant_name and participant.name != participant_name:
            participant.name = participant_name
            update_fields.append('name')

        existing_roles = []
        try:
            parsed_existing_roles = json.loads(participant.roles_json or '[]')
            if isinstance(parsed_existing_roles, list):
                existing_roles = [str(role).strip() for role in parsed_existing_roles if str(role).strip()]
        except Exception:
            existing_roles = []

        merged_roles = list(existing_roles)
        for role in normalized_roles:
            if role not in merged_roles:
                merged_roles.append(role)

        merged_roles_json = json.dumps(merged_roles)
        if participant.roles_json != merged_roles_json:
            participant.roles_json = merged_roles_json
            update_fields.append('roles_json')

        normalized_image_url = str(image_url or '').strip()[:500]
        if normalized_image_url and participant.image_url != normalized_image_url:
            participant.image_url = normalized_image_url
            update_fields.append('image_url')

        participant.save(update_fields=list(dict.fromkeys(update_fields)))
