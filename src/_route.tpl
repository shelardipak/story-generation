{{/* PAS OpenShift Route resource template */}}
{{- define "route" }}
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ .name }}
  labels:
    compound: {{ .compoundName | quote }}
    layer: {{ .layerName | quote }}
    step: {{ .stepName | quote }}
    version: {{ .compoundVersion | quote }}
    {{- if .labels }}
    {{- range $key, $val := .labels }}
    {{ $key }}: {{ $val | quote }}
    {{- end }}
    {{- end }}
spec:
  host: {{ .host }}
  {{- if .targetPort }}
  port:
    targetPort: {{ .targetPort }}
  {{- end }}
  tls:
    insecureEdgeTerminationPolicy: Redirect
    termination: {{ .tlsTermination | default "edge" }}
  to:
    kind: Service
    name: {{ .serviceName }}
    weight: 100
status:
{{- end }}
