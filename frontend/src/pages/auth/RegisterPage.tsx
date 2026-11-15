/**
 * Self-registration screen.
 *
 * Two things are worth noting:
 *
 * * **Password confirmation is validated client-side** with zod, mirroring the serializer's own
 *   check — the server still enforces it, but a mismatched confirmation should not need a round trip.
 * * **The password rules belong to the server.** Django's `AUTH_PASSWORD_VALIDATORS` are the source
 *   of truth, and they can change without a frontend release, so the form checks only the minimum
 *   it can guarantee (length, confirmation) and renders whatever the `password` field error says.
 *   Duplicating the full validator list here would drift and start rejecting valid passwords.
 */

import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '../../components/ui/Button'
import { Input, applyFieldErrors } from '../../components/ui/Field'
import { FormAlert } from '../../components/ui/States'
import { useRegister } from '../../features/auth/hooks'
import { useToast } from '../../components/toast/ToastProvider'

const registerSchema = z
  .object({
    full_name: z.string().min(1, 'Enter your full name.').max(150, 'Use at most 150 characters.'),
    email: z.string().min(1, 'Enter your email address.').email('Enter a valid email address.'),
    password: z.string().min(8, 'Use at least 8 characters.'),
    password_confirm: z.string().min(1, 'Confirm your password.'),
  })
  .refine((values) => values.password === values.password_confirm, {
    path: ['password_confirm'],
    message: 'The passwords do not match.',
  })

type RegisterValues = z.infer<typeof registerSchema>

export function RegisterPage() {
  const navigate = useNavigate()
  const register = useRegister()
  const toast = useToast()

  const {
    register: field,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: '', email: '', password: '', password_confirm: '' },
  })

  useEffect(() => {
    if (!register.isSuccess) return
    // Registration deliberately does not create a session, so send the user to sign in.
    toast.success('Account created', 'Sign in with your new credentials.')
    navigate('/login', { replace: true })
  }, [register.isSuccess, navigate, toast])

  useEffect(() => {
    if (register.isError) applyFieldErrors(register.error, setError)
  }, [register.isError, register.error, setError])

  return (
    <div className="auth-layout">
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="sidebar__mark" aria-hidden="true">
            ET
          </span>
          <div>
            <p className="auth-card__title">Create your account</p>
            <p className="auth-card__subtitle">New accounts start as reporters.</p>
          </div>
        </div>

        <form
          className="auth-card__form"
          onSubmit={handleSubmit((values) => register.mutate(values))}
          noValidate
        >
          <FormAlert error={register.isError ? register.error : null} />

          <Input
            label="Full name"
            autoComplete="name"
            autoFocus
            placeholder="Ada Lovelace"
            error={errors.full_name?.message}
            {...field('full_name')}
          />
          <Input
            label="Email"
            type="email"
            autoComplete="username"
            placeholder="you@example.com"
            error={errors.email?.message}
            {...field('email')}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            hint="At least 8 characters."
            error={errors.password?.message}
            {...field('password')}
          />
          <Input
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            error={errors.password_confirm?.message}
            {...field('password_confirm')}
          />

          <Button type="submit" variant="primary" size="lg" fullWidth loading={register.isPending}>
            Create account
          </Button>
        </form>

        <p className="auth-card__footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
