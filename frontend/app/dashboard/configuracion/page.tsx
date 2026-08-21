"use client"

import { useState, useEffect } from "react"
import { User, Phone, CreditCard, Save, CheckCircle, AlertCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { authService } from "@/lib/services/auth"
import { useAuth } from "@/contexts/auth-context"

const ID_TYPES = [
  { value: "CC",  label: "Cédula de Ciudadanía (CC)" },
  { value: "CE",  label: "Cédula de Extranjería (CE)" },
  { value: "NIT", label: "NIT" },
  { value: "PP",  label: "Pasaporte (PP)" },
]

export default function ConfiguracionPage() {
  const { user: authUser, refreshUser } = useAuth()

  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    identification_type: "CC",
    identification_number: "",
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (authUser) {
      setForm({
        full_name:             authUser.full_name ?? "",
        phone:                 authUser.phone ?? "",
        identification_type:   authUser.identification_type ?? "CC",
        identification_number: authUser.identification_number ?? "",
      })
    }
  }, [authUser])

  function set(field: string, value: string) {
    setForm(f => ({ ...f, [field]: value }))
    setSaved(false)
    setError(null)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      await authService.updateProfile(form)
      if (refreshUser) await refreshUser()
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      setError("No se pudo guardar el perfil. Intenta de nuevo.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Configuración</h1>
        <p className="text-sm text-gray-500 mt-1">Administra tu perfil e información personal</p>
      </div>

      {/* Datos de cuenta */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <User className="w-4 h-4" />
            Datos de cuenta
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Nombre completo
            </label>
            <Input
              value={form.full_name}
              onChange={e => set("full_name", e.target.value)}
              placeholder="Tu nombre completo"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Correo electrónico
            </label>
            <Input
              value={authUser?.email ?? ""}
              disabled
              className="bg-gray-50 text-gray-500"
            />
            <p className="text-xs text-gray-400 mt-1">El correo no se puede cambiar</p>
          </div>
        </CardContent>
      </Card>

      {/* Identificación */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CreditCard className="w-4 h-4" />
            Identificación
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
            Estos datos se usan para la consulta automática de facturas en portales como <strong>Gas GDO</strong>.
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Tipo de identificación
            </label>
            <select
              value={form.identification_type}
              onChange={e => set("identification_type", e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {ID_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Número de identificación
            </label>
            <Input
              value={form.identification_number}
              onChange={e => set("identification_number", e.target.value)}
              placeholder="Ej: 1112041916"
            />
          </div>
        </CardContent>
      </Card>

      {/* Contacto */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Phone className="w-4 h-4" />
            Contacto
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">
              Teléfono / Móvil
            </label>
            <Input
              value={form.phone}
              onChange={e => set("phone", e.target.value)}
              placeholder="Ej: 3126266746"
              type="tel"
            />
          </div>
        </CardContent>
      </Card>

      {/* Guardar */}
      {error && (
        <div className="flex items-center gap-2 text-red-600 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}
      <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto">
        {saving ? (
          <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Guardando...</>
        ) : saved ? (
          <><CheckCircle className="w-4 h-4 mr-2 text-green-500" />Guardado</>
        ) : (
          <><Save className="w-4 h-4 mr-2" />Guardar cambios</>
        )}
      </Button>
    </div>
  )
}
