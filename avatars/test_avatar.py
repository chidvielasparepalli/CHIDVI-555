from avatars.avatar_service import avatar_service

print("===== Avatar Test =====")

avatar_service.idle()

avatar_service.listening()

avatar_service.thinking()

avatar_service.speaking()

avatar_service.happy()

avatar_service.blush()

avatar_service.sad()

print("Current State:", avatar_service.get_state())