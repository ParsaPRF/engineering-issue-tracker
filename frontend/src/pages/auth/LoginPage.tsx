/**
 * Sign-in screen.
 *
 * Follows the redirect contract: `ProtectedRoute` sends an anonymous visitor to
 * `/login?next=<path>`, and a successful login returns them to that path. `next` is only honoured
 * when it is a site-relative path — an absolute URL would turn the login page into an open
 * redirect, which is a phishing primitive.
 */

import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '../../components/ui/Button'
import { Input, applyFieldErrors } from '../../components/ui/Field'
import { FormAlert } from '../../components/ui/States'
import { useLogin } from '../../features/auth/hooks'

const loginSchema = z.object({
  email: z.string().min(1, 'Enter your email address.').email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
})

type LoginValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const login = useLogin()
  const rawNext = searchParams.get('next')
  // Only a path on this site is a valid destination; anything else falls back to the dashboard.
  const next = rawNext && rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/'

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  useEffect(() => {
    if (login.isSuccess) navigate(next, { replace: true })
  }, [login.isSuccess, navigate, next])

  useEffect(() => {
    if (login.isError) applyFieldErrors(login.error, setError)
  }, [login.isError, login.error, setError])

  return (
    <div className="auth-layout">
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="sidebar__mark" aria-hidden="true">
            ET
          </span>
          <div>
            <p className="auth-card__title">Eng Tracker</p>
            <p className="auth-card__subtitle">Engineering issue tracking</p>
          </div>
        </div>

        <form
          className="auth-card__form"
          onSubmit={handleSubmit((values) => login.mutate(values))}
          noValidate
        >
          <FormAlert error={login.isError ? login.error : null} />

          <Input
            label="Email"
            type="email"
            autoComplete="username"
            autoFocus
            placeholder="you@example.com"
            error={errors.email?.message}
            {...register('email')}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            error={errors.password?.message}
            {...register('password')}
          />

          <Button type="submit" variant="primary" size="lg" fullWidth loading={login.isPending}>
            Sign in
          </Button>
        </form>

        <p className="auth-card__footer">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  )
}
