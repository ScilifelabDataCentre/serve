from ... import AppInstanceManager, BaseAppInstance
from .base import AbstractCustomAppInstance


class StreamlitAppInstanceManager(AppInstanceManager):
    model_type = "streamlitappinstance"


class StreamlitInstance(AbstractCustomAppInstance, BaseAppInstance):
    objects = StreamlitAppInstanceManager()

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        # TODO Change this to actual command to run gradio app
        k8s_values["appconfig"][
            "startupCommand"
        ] = f"#!/bin/bash\nstreamlit run app.py --server.address=0.0.0.0 --server.port={self.port}"
        return k8s_values

    class Meta:
        verbose_name = "Streamlit App Instance"
        verbose_name_plural = "Streamlit App Instances"
        permissions = [("can_access_app", "Can access app service")]
