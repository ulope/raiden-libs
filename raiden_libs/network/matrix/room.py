from cachetools.func import ttl_cache
from matrix_client.errors import MatrixRequestError
from matrix_client.room import Room as MatrixRoom
from typing import List

from matrix_client.user import User

from .utils import geventify_callback
from ethereum.slogging import getLogger

log = getLogger(__name__)


class Room(MatrixRoom):
    """ Matrix `Room` subclass that invokes listener callbacks in separate greenlets """

    def __init__(self, client, room_id):
        super().__init__(client, room_id)
        self._members = {}

    def add_listener(self, callback, event_type=None):
        return super().add_listener(geventify_callback(callback), event_type)

    def add_ephemeral_listener(self, callback, event_type=None):
        return super().add_ephemeral_listener(geventify_callback(callback), event_type)

    def add_state_listener(self, callback, event_type=None):
        super().add_state_listener(geventify_callback(callback), event_type)

    @ttl_cache(ttl=10)
    def get_joined_members(self) -> List[User]:
        """ Return a list of members of this room. """
        response = self.client.api.get_room_members(self.room_id)
        for event in response['chunk']:
            if event['content']['membership'] == 'join':
                user_id = event["state_key"]
                if user_id not in self._members:
                    self._mkmembers(
                        User(
                            self.client.api,
                            user_id,
                            event['content'].get('displayname')
                        )
                    )
        return list(self._members.values())

    def _mkmembers(self, member):
        if member.user_id not in self._members:
            self._members[member.user_id] = member

    def _rmmembers(self, user_id):
        self._members.pop(user_id, None)

    def __repr__(self):
        if self.canonical_alias:
            return f'<Room alias="{self.canonical_alias}">'
        return f'<Room id="{self.room_id}" aliases={self.aliases!r}>'

    def update_aliases(self):
        """ Get aliases information from room state

        Returns:
            boolean: True if the aliases changed, False if not
        """
        changed = False
        try:
            response = self.client.api.get_room_state(self.room_id)
        except MatrixRequestError:
            return False
        for chunk in response:
            content = chunk.get('content')
            if content:
                if 'aliases' in content:
                    aliases = content['aliases']
                    if aliases != self.aliases:
                        self.aliases = aliases
                        changed = True
                if chunk.get('type') == 'm.room.canonical_alias':
                    canonical_alias = content['alias']
                    if self.canonical_alias != canonical_alias:
                        self.canonical_alias = canonical_alias
                        changed = True
        if changed and self.aliases and not self.canonical_alias:
            self.canonical_alias = self.aliases[0]
        return changed
