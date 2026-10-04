-- Migration: 20261002000009_tighten_internal_helper_rpc.sql
-- Description: Revoke direct RPC execution on internal RLS helper functions from authenticated role

REVOKE EXECUTE ON FUNCTION public.get_current_user_role() FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.get_mechanic_id_for_user(uuid) FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.is_admin() FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.is_admin_or_support() FROM authenticated;
