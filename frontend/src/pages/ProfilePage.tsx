/**
 * Profile: view and edit the caller's own account.
 *
 * The payload shape mirrors `MeUpdateSerializer`: `full_name` sits at the top level while the other
 * four fields sit under `profile`. Sending them flat would be silently ignored by the serializer —
 * which is exactly the kind of "it saved nothing and said nothing" failure this form avoids by
 * constructing the nested object explicitly.
 *
 * Email and system role are read-only here because the API does not accept them on this endpoint:
 * a user cannot change their own login identifier or promote themselves.
 */

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, MetaRow, PageHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Checkbox, Input, applyFieldErrors } from '../components/ui/Field';
import { FormAlert, LoadingState } from '../components/ui/States';
import { Badge, RoleBadge } from '../components/ui/Badge';
import { useAuthContext } from '../features/auth/hooks/useAuthContext';
import { useChangePassword, useUpdateMe } from '../features/auth/hooks';
import { formatDate, roleLabel } from '../lib/format';

const profileSchema = z.object({
  full_name: z.string().trim().min(1, 'Enter your full name.').max(150, 'Use at most 150 characters.'),
  job_title: z.string().max(120, 'Use at most 120 characters.'),
  phone: z.string().max(40, 'Use at most 40 characters.'),
  // Free text: the backend validates against the IANA database and returns a field error naming the
  // problem. A hard-coded list here would go stale and reject valid zones.
  timezone: z.string().max(64, 'Use at most 64 characters.'),
  notify_on_assignment: z.boolean(),
  notify_on_comment: z.boolean(),
  notify_on_status_change: z.boolean(),
});

type ProfileValues = z.infer<typeof profileSchema>;

export function ProfilePage() {
  const { user } = useAuthContext();
  const update = useUpdateMe();

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isDirty },
  } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    values: {
      full_name: user?.full_name ?? '',
      job_title: user?.profile.job_title ?? '',
      phone: user?.profile.phone ?? '',
      timezone: user?.profile.timezone ?? '',
      notify_on_assignment: user?.profile.notify_on_assignment ?? true,
      notify_on_comment: user?.profile.notify_on_comment ?? true,
      notify_on_status_change: user?.profile.notify_on_status_change ?? true,
    },
  });

  useEffect(() => {
    if (update.isError) applyFieldErrors(update.error, setError);
  }, [update.isError, update.error, setError]);

  if (!user) return <LoadingState label="Loading your profile…" />;

  const onSubmit = handleSubmit((values) => {
    update.mutate({
      full_name: values.full_name,
      profile: {
        job_title: values.job_title,
        phone: values.phone,
        timezone: values.timezone,
        notify_on_assignment: values.notify_on_assignment,
        notify_on_comment: values.notify_on_comment,
        notify_on_status_change: values.notify_on_status_change,
      },
    });
  });

  const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <>
      <PageHeader
        title="Profile"
        subtitle="Your account details and notification preferences."
        actions={
          <Button variant="primary" loading={update.isPending} disabled={!isDirty} onClick={() => void onSubmit()}>
            Save changes
          </Button>
        }
      />

      <div className="stack">
        <div className="grid grid--sidebar">
          <Card title="Account">
            <form className="stack" onSubmit={(event) => { event.preventDefault(); void onSubmit(); }} noValidate>
              <FormAlert error={update.isError ? update.error : null} />

              <Input
                label="Full name"
                required
                error={errors.full_name?.message}
                {...register('full_name')}
              />

              <div className="form-grid form-grid--2">
                <Input label="Job title" error={errors.job_title?.message} {...register('job_title')} />
                <Input
                  label="Phone"
                  type="tel"
                  placeholder="+1 555 0100"
                  error={errors.phone?.message}
                  {...register('phone')}
                />
              </div>

              <Input
                label="Timezone"
                hint={`IANA name, e.g. Europe/Berlin. Your browser reports ${browserTimezone}.`}
                error={errors.timezone?.message}
                {...register('timezone')}
              />

              <div className="field">
                <span className="field__label">Notifications</span>
                <div className="stack stack--tight">
                  <Checkbox label="Email me when a ticket is assigned to me" {...register('notify_on_assignment')} />
                  <Checkbox label="Email me when someone comments on my tickets" {...register('notify_on_comment')} />
                  <Checkbox label="Email me when a ticket's status changes" {...register('notify_on_status_change')} />
                </div>
                <span className="field__hint">
                  In-app notifications are always recorded; these control the email copies.
                </span>
              </div>

              <div className="form-actions">
                <Button type="submit" variant="primary" loading={update.isPending} disabled={!isDirty}>
                  Save changes
                </Button>
              </div>
            </form>
          </Card>

          <aside className="detail-aside">
            <Card title="Identity">
              <div className="meta-list">
                <MetaRow label="Email">{user.email}</MetaRow>
                <MetaRow label="System role">
                  <RoleBadge role={user.system_role} label={roleLabel(user.system_role)} />
                </MetaRow>
                <MetaRow label="Status">
                  {user.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="outline">Inactive</Badge>}
                </MetaRow>
                <MetaRow label="Joined">{formatDate(user.date_joined)}</MetaRow>
              </div>
              <p className="field__hint" style={{ marginTop: 'var(--space-3)' }}>
                Email addresses and system roles are managed by an administrator; they cannot be changed
                from here.
              </p>
            </Card>

            <Card title="My projects" subtitle={`${user.memberships.length} membership(s)`}>
              {user.memberships.length === 0 ? (
                <p className="field__hint">You are not a member of any project yet.</p>
              ) : (
                <div className="meta-list">
                  {user.memberships.map((membership) => (
                    <MetaRow key={membership.project_id} label={membership.project_key}>
                      <span className="row row--nowrap" style={{ justifyContent: 'flex-end' }}>
                        <span>{membership.project_name}</span>
                        <Badge tone={membership.role === 'MANAGER' ? 'accent' : 'neutral'}>
                          {roleLabel(membership.role)}
                        </Badge>
                        {membership.is_active ? null : <Badge tone="outline">inactive</Badge>}
                      </span>
                    </MetaRow>
                  ))}
                </div>
              )}
            </Card>
          </aside>
        </div>

        <ChangePasswordCard />
      </div>
    </>
  );
}

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(8, 'Use at least 8 characters.'),
    new_password_confirm: z.string().min(1, 'Confirm the new password.'),
  })
  .refine((values) => values.new_password === values.new_password_confirm, {
    path: ['new_password_confirm'],
    message: 'The passwords do not match.',
  });

type PasswordValues = z.infer<typeof passwordSchema>;

/**
 * Password change.
 *
 * The server re-establishes the current session after invalidating the others, so the user is not
 * signed out of the tab they are working in. That is why the success path only clears the form.
 */
function ChangePasswordCard() {
  const change = useChangePassword();
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', new_password_confirm: '' },
  });

  useEffect(() => {
    if (change.isError) applyFieldErrors(change.error, setError);
  }, [change.isError, change.error, setError]);

  const onSubmit = handleSubmit((values) => {
    change.mutate(values, {
      onSuccess: () => {
        reset();
        setDone(true);
      },
    });
  });

  const passwordError = change.isError && change.error instanceof Error && !hasFieldErrors(change.error)
    ? change.error
    : null;

  return (
    <Card title="Change password" subtitle="Changing your password signs out your other sessions.">
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void onSubmit(); }} noValidate>
        <FormAlert error={passwordError} />
        {done && !change.isError ? (
          <p className="form-alert" role="status" style={{ borderColor: 'var(--color-success-border)', background: 'var(--color-success-soft)', color: 'var(--green-700)' }}>
            Password changed. Your other sessions have been signed out.
          </p>
        ) : null}

        <div className="form-grid form-grid--2">
          <Input
            label="Current password"
            type="password"
            autoComplete="current-password"
            error={errors.current_password?.message}
            {...register('current_password')}
          />
          <Input
            label="New password"
            type="password"
            autoComplete="new-password"
            error={errors.new_password?.message}
            {...register('new_password')}
          />
          <Input
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            error={errors.new_password_confirm?.message}
            {...register('new_password_confirm')}
          />
        </div>

        <div className="form-actions">
          <Button type="submit" variant="primary" loading={change.isPending}>
            Change password
          </Button>
        </div>
      </form>
    </Card>
  );
}

/**
 * True when the error was mapped onto a field, so the banner does not repeat it.
 *
 * `ApiError.fields` is the map `applyFieldErrors` consumed; when it is non-empty the messages are
 * already under the right inputs.
 */
function hasFieldErrors(error: unknown): boolean {
  if (!(error instanceof Object) || !('fields' in error)) return false;
  const fields = (error as { fields?: Record<string, string[]> }).fields;
  return Boolean(fields && Object.keys(fields).length > 0);
}
