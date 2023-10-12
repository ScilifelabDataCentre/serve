from dataclasses import dataclass
from typing import Optional, Sequence
import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import EmailValidator
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from django import forms
from django.db import transaction
from common.models import UserProfile


DEPARTMENTS = (
        "Biology Education Centre",
"Centre for Gender Research",
"Department of ALM (Archives, Library, and Museum Studies)",
"Department of Archaeology and Ancient History",
"Department of Art History",
"Department of Business Studies",
"Department of Chemistry - Ångström Laboratory",
"Department of Chemistry - BMC",
"Department of Civil and Industrial Engineering",
"Department of Cultural Anthropology and Ethnology",
"Department of Earth Sciences",
"Department of Economic History",
"Department of Economics",
"Department of Education",
"Department of Electrical Engineering",
"Department of English",
"Department of Food Studies, Nutrition and Dietetics",
"Department of Game Design",
"Department of Government",
"Department of History",
"Department of History of Science and Ideas",
"Department of Human Geography",
"Department of Immunology, Genetics and Pathology",
"Department of Informatics and Media",
"Department of Information Technology",
"Department of Law",
"Department of Linguistics and Philology",
"Department of Literature",
"Department of Materials Science and Engineering",
"Department of Mathematics",
"Department of Medical Biochemistry and Microbiology",
"Department of Medical Cell Biology",
"Department of Medical Sciences",
"Department of Medicinal Chemistry",
"Department of Modern Languages",
"Department of Musicology",
"Department of Peace and Conflict Research",
"Department of Pharmaceutical Biosciences",
"Department of Pharmacy",
"Department of Philosophy",
"Department of Physics and Astronomy",
"Department of Psychology",
"Department of Public Health and Caring Sciences",
"Department of Scandinavian Languages",
"Department of Sociology",
"Department of Statistics",
"Department of Surgical Sciences",
"Department of Theology",
"Department of Women's and Children's Health",
"Faculty of Engineering, LTH",
"Faculty of Fine and Performing Arts",
"Faculties of Humanities and Theology",
"Faculty of Law",
"Faculty of Medicine",
"Faculty of Science",
"Faculty of Social Sciences",
"School of Economics and Management, LUSEM",
"Campus Helsingborg",
"School of Aviation",
"Department of Archaeology and Classical Studies",
"Department of Asian and Middle Eastern Studies",
"Department of English",
"Department of Ethnology, History of Religions and Gender Studies",
"Department of History",
"Department of Culture and Aesthetics",
"Department of Linguistics",
"Department of Media Studies",
"Department of Philosophy",
"Department of Romance Studies and Classics",
"Department of Slavic and Baltic Studies, Finnish, Dutch and German",
"Department of Swedish Language and Multilingualism",
"Department of Teaching and Learning",
"Department of Law",
"Department of Computer and Systems Sciences",
"Department of Child and Youth Studies",
"Department of Criminology",
"Department of Economic History and International Relations",
"Department of Economics",
"Department of Education",
"Department of Human Geography",
"Department of Political Science",
"Department of Psychology",
"Department of Public Health Sciences",
"Department of Social Anthropology",
"Department of Social Work",
"Department of Sociology",
"Department of Special Education",
"Department of Statistics",
"Department of Astronomy",
"Department of Mathematics",
"Department of Meteorology (MISU)",
"Department of Physics",
"Department of Biochemistry and Biophysics (DBB)",
"Department of Organic Chemistry",
"Department of Materials and Environmental Chemistry (MMK)",
"Department of Biology Education (BIG)",
"Department of Molecular Biosciences, The Wenner-Gren Institute",
"Department of Ecology, Environment and Plant Sciences (DEEP)",
"Department of Zoology",
"Department of Environmental Science",
"Department of Geological Sciences",
"Department of Physical Geography",
"Arctic Centre at Umeå University",
"Bildmuseet (Museum of Contemporary Art and Visual Culture)",
"Biobank Research Unit",
"Campus Services Office",
"Centre for Biomedical Engineering and Physics (CMTF)",
"Centre for Demographic and Ageing Research at Umeå University (CEDAR)",
"Centre for Digital Social Research (DIGSUM)",
"Centre for Educational Development",
"Centre for Environmental and Resource Economics (CERE)",
"Centre for Principal Development",
"Centre for Regional Science at Umeå University",
"Centre for Sami Research (Cesam) - Várdduo",
"Centre for Sustainable Cement and Quicklime Production",
"Centre for Transdisciplinary AI",
"Climate Impacts Research Centre (CIRC)",
"Communications Office",
"Curiosum",
"Department of Applied Educational Science",
"Department of Applied Physics and Electronics",
"Department of Chemistry",
"Department of Clinical Microbiology",
"Department of Clinical Sciences",
"Department of Community Medicine and Rehabilitation",
"Department of Computing Science",
"Department of Creative Studies (Teacher Education)",
"Department of Culture and Media Studies",
"Department of Ecology and Environmental Science",
"Department of Education",
"Department of Epidemiology and Global Health",
"Department of Food, Nutrition and Culinary Science",
"Department of Geography",
"Department of Historical, Philosophical and Religious Studies",
"Department of Informatics",
"Department of Integrative Medical Biology (IMB)",
"Department of Language Studies",
"Department of Law",
"Department of Mathematics and Mathematical Statistics",
"Department of Medical Biochemistry and Biophysics",
"Department of Medical Biosciences",
"Department of Molecular Biology",
"Department of Nursing",
"Department of Odontology",
"Department of Physics",
"Department of Plant Physiology",
"Department of Political Science",
"Department of Psychology",
"Department of Public Health and Clinical Medicine",
"Department of Radiation Sciences",
"Department of Science and Mathematics Education",
"Department of Social Work",
"Department of Sociology",
"Department of Surgical and Perioperative Sciences",
"Department of Biosciences and Nutrition",
"Department of Cell and Molecular Biology",
"Department of Clinical Neuroscience",
"Department of Clinical Science and Education, Södersjukhuset",
"Department of Clinical Science, Intervention and Technology",
"Department of Clinical Sciences, Danderyd Hospital",
"Department of Dental Medicine",
"Department of Global Public Health",
"Department of Laboratory Medicine",
"Department of Learning, Informatics, Management and Ethics",
"Department of Medical Biochemistry and Biophysics",
"Department of Medical Epidemiology and Biostatistics",
"Department of Medicine, Huddinge",
"Department of Medicine, Solna",
"Department of Microbiology, Tumor and Cell Biology",
"Department of Molecular Medicine and Surgery",
"Department of Neurobiology, Care Sciences and Society",
"Department of Neuroscience",
"Department of Oncology-Pathology",
"Department of Physiology and Pharmacology",
"Department of Women's and Children's Health",
"Institute of Environmental Medicine",
"Architecture and the Built Environment",
"Architecture",
"Civil and Architectural Engineering",
"Philosophy and History",
"Real Estate and Construction Management",
"Sustainable Development, Environmental Science and Engineering",
"Urban Planning and Environment",
"Electrical Engineering and Computer Science",
"Computer Science",
"Electrical Engineering",
"Human Centered Technology",
"Intelligent Systems",
"Industrial Engineering and Management",
"Engineering Design",
"Energy Technology",
"Industrial economics and management",
"Learning",
"Materials Science and Engineering",
"Production Engineering",
"Engineering Sciences in Chemistry, Biotechnology and Health",
"Biomedical Engineering and Health Systems",
"Chemical Engineering",
"Chemistry",
"Fibre and Polymer Technology",
"Gene Technology",
"Industrial Biotechnology",
"Protein Science",
"Engineering Science",
"Applied Physics",
"Engineering Mechanics",
"Mathematics",
"Physics",
"Architecture and Civil Engineering",
"Computer Science and Engineering",
"Electrical Engineering",
"Physics",
"Industrial and Materials Science",
"Chemistry and Chemical Engineering",
"Life Sciences",
"Mathematical Sciences",
"Mechanics and Maritime Sciences",
"Microtechnology and Nanoscience",
"Space, Earth and Environment",
"Technology Management and Economics",
"Communication and Learning in Science",
"Department of Computer Science, Electrical and Space Engineering",
"Department of Engineering Sciences and Mathematics",
"Department of Health, Education and Technology",
"Department of Social Sciences, Technology and Arts",
"Dept. of Civil, Environmental and Natural Resources Engineering",
"Department of Accounting",
"Department of Economics",
"Department of Entrepreneurship, Innovation & Technology",
"Department of Finance",
"Department of Management and Organization",
"Department of Marketing and Strategy",
"Department of Anatomy, Physiology and Biochemistry",
"Department of Animal Breeding and Genetics",
"Department of Animal Environment and Health",
"Department of Animal Nutrition and Management",
"Department of Aquatic Resources (SLU Aqua)",
"Department of Aquatic Sciences and Assessment",
"Department of Biomedical Sciences and Veterinary Public Health",
"Department of Biosystems and Technology",
"Department of Clinical Sciences",
"Department of Crop Production Ecology",
"Department of Ecology",
"Department of Economics",
"Department of Energy and Technology",
"Department of Forest Biomaterials and Technology",
"Department of Forest Ecology and Management",
"Department of Forest Economics",
"Department of Forest Genetics and Plant Physiology",
"Department of Forest Mycology and Plant Pathology",
"Department of Forest Resource Management",
"Department of Landscape Architecture, Planning and Management",
"Department of Molecular Sciences",
"Department of People and Society",
"Department of Plant Biology",
"Department of Plant Breeding",
"Department of Plant Protection Biology",
"Department of Soil and Environment",
"Department of Urban and Rural Development",
"Department of Wildlife, Fish, and Environmental Studies",
"Equine Science Unit",
"School for Forest Management",
"Southern Swedish Forest Research Centre",
"Unit for Field-based Forest Research",
"Faculty of Forest Sciences",
"Faculty of Landscape Architecture, Horticulture and Crop Production Sciences",
"Faculty of Natural Resources and Agricultural Sciences",
"Faculty of Veterinary Medicine and Animal Science",
"Faculty of Arts and Social Sciences",
"Faculty of Health, Science and Technology",
"The Faculty Board for Teacher Education",
"Karlstad Business School",
"Department of Artistic Studies",
"Department of Political, Historical, Religious and Cultural Studies",
"Department of Social and Psychological Studies",
"Department of Language, Literature and Intercultural Studies",
"Department of Geography, Media and Communication",
"Department of Educational Studies",
"Department of Environmental and Life Sciences",
"Department of Health Sciences",
"Department of Engineering and Chemical Sciences",
"Department of Engineering and Physics",
"Department of Mathematics and Computer Science",
"Faculty of Health and Life Sciences",
"Department of Biology and Environmental Science",
"Department of Chemistry and Biomedical Sciences",
"Department of Health and Caring Sciences",
"Department of Medicine and Optometry",
"Department of Psychology",
"Faculty of Arts and Humanities",
"Faculty of Social Sciences",
"Faculty of Technology",
"University Library",
"Faculty of Business, Science and Engineering",
"Faculty of Humanities and Social Sciences",
"Faculty of Medicine and Health",
"School of Behavioural, Social and Legal Sciences",
"School of Business",
"School of Health Sciences",
"School of Hospitality, Culinary Arts and Meal Science",
"School of Humanities, Education and Social Sciences",
"School of Medical Sciences",
"School of Music, Theatre and Art",
"School of Science and Technology",
"Department of Computer and Electrical Engineering",
"Department of Economics, Geography, Law and Tourism",
"Department of Humanities and Social Sciences",
"Department of Health Sciences",
"Department of Engineering, Mathematics and Science Education",
"Department of Communication, Quality Management and Information Systems",
"Department of Natural Science, Design and Sustainable Development",
"Department of Psychology and Social Work (PSO)",
"Department of Education",
"Division for Student Affairs",
"Division of Academic Quality Support",
"Division of Admissions and Degrees",
"Division of Campus Affairs",
"Division of Communications",
"Division of Finance and Purchase",
"Division of Human Resources",
"Division of Planning, Finance and Accounting",
"Division of School Offices",
"IT-Division",
"Library",
"Management Office",
"Office for Research, Collaboration and Innovation Support",
"School of Business Society and Engineering",
"School of Education, Culture and Communication",
"School of Health, Care and Social Welfare",
"School of Innovation, Design and Engineering",
"The University management",
"Department of Computer Science",
"Department of Software Engineering",
"Department of Technology and Aesthetics",
"Department of Spatial Planning",
"Department of Health",
"Department of Industrial Economics",
"Department of Mechanical Engineering",
"Department of Mathematics and Natural Sciences",
"Department of Strategic Sustainable Development",
"Department of Leadership and Command & Control",
"Department of Political Science and Law",
"Department of Systems Science for Defence and Security",
"Department of War Studies and Military History",
"Centre for Societal Security",
"Higher Joint Command and Staff Programme Directorate",
"Officers´ Programme Directorate",
"Physical activity and brain health, E-PABS",
"Sport Performance and Exercise Research & Innovation Center-Stockholm, SPERIC-S",
"The HPI group",
"Steering Committee ",
"Higher Education Management",
"Central Administration",
"School of Information and Engineering",
"School of Language, Literatures and Learning",
"School of Culture and Society",
"School of Teacher Education",
"School of Health and Welfare",
"Other",
"Department of Economics",
"Business Economics",
"Law",
"National Economics",
"Department of Humanities",
"English",
"Gender Studies",
"Media and Communication Studies",
"Religious Studies",
"Swedish Language",
"Department of Educational Sciences",
"Visual Education",
"School of Business, Innovation and Sustainability",
"School of Education, Humanities and Social Sciences",
"School of Health and Welfare",
"School of Information Technology",
"Faculty of Education",
"Faculty of Health Science",
"Faculty of Natural Science",
"Faculty of Business",
"Department of Nursing and Integrated Health Sciences",
"Department of Business",
"Governance Regulation Internationalization and Performance",
"Department of Secondary Teacher Education",
"Man - Health - Society",
"Learning in Science and Mathematics",
"Man and Biosphere Health",
"Research on relational pedagogy",
"Barndom Lärande och Utbildning",
"Patient Reported Outcomes - Clinical Assessment Research and Education",
"Sustainable multifunctional landscapes",
"Department of Environmental Science",
"Research environment Individual Group Society",
"Learning in Language and Literature",
"Department of Early Years Education",
"Research environment of Computer science",
"Department of Food and Meal Science",
"Department of Primary Teacher Education",
"Department of Computer Science",
"Childrens and Young Peoples Health in Social Context",
"Food and Meals in Everyday Life",
"Department of Work Science",
"Department of Bioanalysis",
"Department of Psychology",
"Department of Special Education",
"Biomedicinsk vetenskap",
"Design A_ Research Collaboration",
"Nominations Committee",
"Oral Health - Public Health - Quality of Life",
"Department of Public Health",
"Department of Design",
"Department of Oral Health",
"Department of Social Sciences",
"University Administration and Services",
"Centrum för Mat Hälsa och Handel Högskolan Kristianstad",
"Library and Higher Education Development",
"Department of After School Education",
"Biomedicin",
"Environmental Analytical Laboratory",
"Imagine innovation team",
"Collaboration and innovation office",
"The School of Bioscience",
"The School of Business",
"The School of Health Sciences",
"The School of Informatics",
"The School of Engineering Science ",
"Department of Social and Behavioural Studies",
"School of Business, Economics and IT",
"Department of Health Sciences",
"Department of Engineering Science",
"Executive office",
"Department of Social Work",
"Department of Natural Science and Biomedicine",
"Department of Nursing Science",
"Department of Rehabilitation",
"Institute of Gerontology",
"Administration",
"School of Historical and Contemporary Studies",
"School of Culture and Education",
"School of Social Sciences",
"School of Natural Sciences, Technology and Environmental Studies",
"School of Police Studies",
)


UNIVERSITIES = (
    ("other", "Other"),
    ("uu", "Uppsala University"),
    ("lu", "Lunds University"),
    ("gu", "Göteborgs University"),
    ("su", "Stockholms University"),
    ("umu", "Umeå University"),
    ("liu", "Linköpings University"),
    ("ki", "(KI) Karolinska institutet"),
    ("kth", "KTH Royal Institute of Technology"),
    ("chalmers", "Chalmers University of Technology"),
    ("ltu", "Luleå University of Technology"),
    ("hhs", "Stockholm School of Economics"),
    ("slu", "Swedish University of Agricultural Sciences"),
    ("kau", "Karlstad University"),
    ("lnu", "Linnaeus University"),
    ("oru", "Örebro University"),
    ("miun", "Mid Sweden University"),
    ("mau", "Malmö University"),
    ("mdu", "Mälardalen University"),
    ("bth", "Blekinge Institute of Technology"),
    ("fhs", "Swedish Defence University"),
    ("gih", "Swedish School of Sport and Health Sciences"),
    ("hb", "University of Borås"),
    ("du", "Dalarna University"),
    ("hig", "University of Gävle"),
    ("hh", "Halmstad University"),
    ("hkr", "Kristianstad University"),
    ("his", "University of Skövde"),
    ("hv", "University West"),
    ("ju", "Jönköping University"),
    ("sh", "Södertörn University"),
)


EMAIL_ALLOW_REGEX = re.compile(
    (r"^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)*?"  # Subdomain part
     f"({('|').join([l[0] for l in UNIVERSITIES[1:]])}"
     ")\.se"  # End of the domain
     "(?:[A-Z0-9-]{0,63}(?<!-))?$"  # Enforce 63-character limit
    ), re.IGNORECASE
)


class ListTextWidget(forms.TextInput):
    def __init__(self, data_list, name, *args, **kwargs):
        super(ListTextWidget, self).__init__(*args, **kwargs)
        self._name = name
        self._list = data_list
        self.attrs.update({'list':'list__%s' % self._name})

    def render(self, name, value, attrs=None, renderer=None):
        text_html = super(ListTextWidget, self).render(name, value, attrs=attrs)
        data_list = '<datalist id="list__%s">' % self._name
        for item in self._list:
            data_list += '<option value="%s">' % item
        data_list += '</datalist>'

        return (text_html + data_list)


class UserForm(UserCreationForm):
    first_name = forms.CharField(
        min_length=1,
        max_length=30,
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name*"}),
    )
    last_name = forms.CharField(
        min_length=1,
        max_length=30,
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name*"}),
    )
    email = forms.EmailField(
        max_length=254,
        label=mark_safe("Use your <a "
                        "href='https://www.uka.se/sa-fungerar-hogskolan/universitet-och-hogskolor/lista-over-"
                        "universitet-hogskolor-och-enskilda-utbildningsanordnare'>"
                        "swedish university</a> email address or submit your request for evaluation."),
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Email*"}),
        label_suffix="",
    )
    password1 = forms.CharField(
        min_length=8,
        label=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password*"}),
    )
    password2 = forms.CharField(
        min_length=8,
        label=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm password*"}),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]
        exclude = [
                "username",
                ]


class ProfileForm(forms.ModelForm):
    affiliation = forms.ChoiceField(
        widget=forms.Select(attrs={"class": "form-control", "placeholder": "University"}),
        label="University affiliation",
        choices=UNIVERSITIES,
        label_suffix="",
    )
    department = forms.CharField(
            widget= ListTextWidget(
               data_list=DEPARTMENTS,
               name='department-list',
               attrs={"class": "form-control", "placeholder": "Department"}
               ),
            label="Select closest department name or enter your own",
            label_suffix="",
            required=False
            )
    why_account_needed = forms.CharField(
            widget=forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Because you are not using Swedish University email, please describe why do you need "
                    "an account.\nYour request will be submited for evaluation.*",
                    "style": "height: 70px"
                    }
                ),
            required=False,
            )
    note = forms.CharField(
            widget=forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": ("If you would like us to get in touch with you, to answer your questions or provide "
                    "help with Serve, please describe what do you need here"),
                    "style": "height: 70px"
                    }
                ),
            required=False,
            )

    class Meta:
        model = UserProfile
        fields = [
            "affiliation",
            "department",
            "note",
            "why_account_needed",
        ]


@dataclass
class SignUpForm:
    user: UserForm
    profile: ProfileForm
    is_approved: bool = False

    def clean(self) -> None:
        self.is_valid()
        user_data = self.user.cleaned_data
        profile_data = self.profile.cleaned_data

        email = user_data.get("email", "")
        affiliation = profile_data.get("affiliation")
        why_account_needed = profile_data.get("why_account_needed")

        user_data["email"] = email.lower()
        affiliation_from_email = email.split("@")[1].split(".")[-2].lower()

        is_university_email = EMAIL_ALLOW_REGEX.match(email.split("@")[1]) is not None
        is_affiliated = affiliation is not None and affiliation != "other"
        is_request_account_empty = not bool(why_account_needed)
        is_department_empty = not bool(profile_data.get("department"))

        self.is_approved = is_university_email

        if is_university_email:
            # Check that selected affiliation is equal to affiliation from email
            if is_affiliated and affiliation != affiliation_from_email:
                self.profile.add_error("affiliation", ValidationError(
                "Email affiliation is different from selected"
                )
                           )
            if not is_affiliated:
                self.profile.add_error("affiliation", ValidationError(
                "You are required to select your affiliation"
                )
                           )
            if is_department_empty:
                self.profile.add_error("department", ValidationError(
                "You are required to select your department"
                )
                           )
        else:
            if is_affiliated:
                self.user.add_error("email", ValidationError(
                    "Email is not from Swedish University. \n"
                    "Please select 'Other' in affiliation or use your University email"
                )
                               )

            if is_request_account_empty:
                self.profile.add_error("why_account_needed", ValidationError(
                    "Please describe why do you need an account"
                )
                               )

    def is_valid(self) -> bool:
        return self.user.is_valid() and self.profile.is_valid()

    def save(self):
        user = self.user.save()
        profile = self.profile.save(commit=False)
        profile.user = user
        profile.is_approved = self.is_approved
        profile.save()
        return profile
