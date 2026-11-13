{{- define "pangolin.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pangolin.labels" -}}
app.kubernetes.io/name: {{ include "pangolin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "pangolin.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pangolin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "pangolin.image" -}}
{{- printf "%s:%s" (required "image.repository is required" .Values.image.repository) (required "image.tag is required" .Values.image.tag) -}}
{{- end -}}
