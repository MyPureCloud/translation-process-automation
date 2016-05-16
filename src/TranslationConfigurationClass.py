import sys, yaml
from TransifexConfigurationClass import TransifexConfiguration

class TranslationConfiguration:
    def __init__(self):
        self._path = str()
        self._config = None
        self._errors = 0

    def parse(self, config_path):
        self._path = config_path
        self._config = TransifexConfiguration()
        with open(config_path, "r") as stream:
            data = yaml.load_all(stream)
            if not self._config.parse(data):
                self._errors += 1

        if self._errors == 0:
            return True
        else:
            return False

    def get_path(self):
        return self._path

    def get_project_name(self):
        return self._config.get_project_name()

    def get_project_platform(self):
        return self._config.get_project_platform()

    def get_project_repository_len(self):
        return self._config.get_project_repository_len()

    def get_project_repository_name(self, repository_index):
        return self._config.get_project_repository_name(repository_index)

    def get_project_repository_platform(self, repository_index):
        return self._config.get_project_repository_platform(repository_index)

    def get_project_repository_owner(self, repository_index):
        return self._config.get_project_repository_owner(repository_index)

    def get_project_repository_config_path(self, repository_index):
        return self._config.get_project_repository_config_path(repository_index)

    def get_project_repository_language(self, repository_index):
        return self._config.get_project_repository_language(repository_index)

    def get_project_reviewers(self):
        return self._config.get_project_reviewers()

    def get_maintainer(self):
        return self._config.get_maintainer()

