from apps.types_.app_types import ModelFormTuple, OptionalModelFormTuple


class AppRegistry:
    def __init__(self):
        self._apps: dict[str, ModelFormTuple] = {}

    def register(self, app_slug: str, app: ModelFormTuple):
        self._apps[app_slug] = app

    def __getitem__(self, app_slug: str) -> OptionalModelFormTuple:
        return self._apps.get(app_slug, (None, None))

    def get(self, app_slug: str) -> OptionalModelFormTuple:
        return self[app_slug]

    def get_apps(self):
        return self._apps

    def get_orm_model(self, app_slug: str):
        return self[app_slug][0]

    def get_form_class(self, app_slug: str):
        return self[app_slug][1]

    def iter_orm_models(self):
        for app in self._apps.values():
            yield app.Model

    def iter_forms(self):
        for app in self._apps.values():
            yield app.Form

    def __contains__(self, item):
        return item in self._apps
