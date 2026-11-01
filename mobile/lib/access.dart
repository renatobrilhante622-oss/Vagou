// Visibility follows server-owned entitlements; endpoints enforce authorization.
bool hasAdminAccess(Map user) =>
    user['is_admin'] == true ||
    const {'super_admin', 'moderator'}.contains(user['role']);
