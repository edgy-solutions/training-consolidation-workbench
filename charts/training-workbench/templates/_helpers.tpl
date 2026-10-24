{{- define "tw.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tw.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "tw.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/name: {{ include "tw.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: training-workbench
{{- end -}}

{{/* Selector labels for one component. Call with (dict "ctx" $ "component" "api"). */}}
{{- define "tw.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tw.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Image reference for one component; a digest wins over a tag, and one of them is required. */}}
{{- define "tw.image" -}}
{{- $img := .values.image -}}
{{- $repo := printf "%s/%s" .ctx.Values.global.imageRegistry $img.name -}}
{{- if $img.digest -}}
{{- printf "%s@%s" $repo $img.digest -}}
{{- else -}}
{{- printf "%s:%s" $repo (required (printf "%s.image.digest or %s.image.tag is required" .component .component) $img.tag) -}}
{{- end -}}
{{- end -}}

{{- define "tw.apiUrl" -}}
{{- if .Values.ui.apiUrl -}}
{{- .Values.ui.apiUrl -}}
{{- else if and .Values.api.ingress.enabled .Values.api.ingress.host -}}
{{- printf "https://%s" .Values.api.ingress.host -}}
{{- end -}}
{{- end -}}
