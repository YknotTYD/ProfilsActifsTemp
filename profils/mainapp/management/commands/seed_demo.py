"""Jeu de donnees de demonstration.

Remplit chaque ecran accessible depuis le frontend avec du contenu credible :
comptes (candidats, recruteurs, un compte administrateur), profils
professionnels complets, deux questionnaires reels avec de vraies questions,
et des tentatives terminees pour que les resultats, les statistiques et les
listes d'admin ne soient jamais vides.

Rejouable : au demarrage, la commande supprime les comptes et questionnaires
qu'elle a elle-meme crees lors d'un run precedent (identifies par une liste de
noms d'utilisateur et de titres fixes), puis les recree. Aucune autre donnee
du site n'est touchee.

Usage :
    python manage.py seed_demo
    docker compose exec web python manage.py seed_demo   # via docker
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from profils.mainapp.models import Role
from profils.profiles import constants as pc
from profils.profiles import services as profile_services
from profils.questionnaires import constants as qc
from profils.questionnaires import services as attempt_services
from profils.questionnaires.editing import create_question, update_question
from profils.questionnaires.models import Questionnaire
from profils.questionnaires.versioning import create_version, publish_version

DEMO_PASSWORD = "Demo1234!"

DEMO_CLIPS = {
    "big_buck_bunny":   "https://www.youtube.com/embed/aqz-KE-bpKQ",
    "sintel":           "https://www.youtube.com/embed/eRsGyueVLvQ",
    "tears_of_steel":   "https://www.youtube.com/embed/R6MlUcmOul8",
    "elephants_dream":  "https://www.youtube.com/embed/TLkA0RELQ1g",
}

RECRUITERS = [
    {"username": "julie.marchand",  "first_name": "Julie",  "last_name": "Marchand",  "birth_date": "1990-03-11"},
    {"username": "paul.guerin",     "first_name": "Paul",   "last_name": "Guérin",    "birth_date": "1985-11-29"},
    {"username": "sophie.lambert",  "first_name": "Sophie", "last_name": "Lambert",   "birth_date": "1992-06-05"},
]

ADMIN_ACCOUNT = {
    "username": "admin_demo", "first_name": "Compte", "last_name": "Administrateur",
    "birth_date": "1988-01-01",
}

CANDIDATES = [
    {
        "username": "camille.dubois", "first_name": "Camille", "last_name": "Dubois",
        "birth_date": "1995-04-12",
        "headline": "Développeuse backend Python/Django",
        "summary": "Six ans d'expérience sur des architectures backend à fort trafic. "
                    "J'aime particulièrement le travail sur les API et la fiabilité des systèmes.",
        "city": "Nantes", "field": pc.FIELD_SOFTWARE,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_CDI, pc.CONTRACT_FREELANCE],
        "work_modes": {"open_to_remote": True, "open_to_hybrid": True},
        "skills": [
            ("Python", pc.LEVEL_EXPERT, 6), ("Django", pc.LEVEL_ADVANCED, 5),
            ("PostgreSQL", pc.LEVEL_ADVANCED, 5), ("Docker", pc.LEVEL_INTERMEDIATE, 3),
            ("Git", pc.LEVEL_EXPERT, 7), ("REST API", pc.LEVEL_ADVANCED, 5),
        ],
        "experiences": [
            {"title": "Développeuse backend", "company": "Doctolib", "start": "2021-03-01",
             "current": True, "skills": ["Python", "Django", "PostgreSQL"],
             "description": "Équipe cœur produit : disponibilité des créneaux et API de réservation."},
            {"title": "Développeuse fullstack", "company": "Younited", "start": "2019-09-01",
             "end": "2021-02-28", "skills": ["Python", "Docker"],
             "description": "Développement de la plateforme de crédit en ligne."},
        ],
        "education": [
            {"institution": "Epitech Nantes", "degree": "Master informatique",
             "level": pc.DEGREE_BAC_5, "start": "2014-09-01", "end": "2019-06-30"},
        ],
        "certifications": [
            {"name": "Certified Kubernetes Application Developer", "issuer": "Cloud Native Computing Foundation",
             "issued": "2023-04-01"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_C1)],
        "projects": [
            {"title": "API de réservation médicale", "role": "Auteure", "skills": ["Python", "PostgreSQL"],
             "description": "API REST open-source de gestion de créneaux, avec verrouillage optimiste."},
        ],
        "links": [("GITHUB", "https://github.com/camilledubois"), ("PORTFOLIO", "https://camilledubois.dev")],
        "video": "big_buck_bunny",
        "q1_answers": {"http_201": True, "db_relational": ["PostgreSQL", "MySQL", "SQLite"], "get_idempotent": "no",
                       "json_format": True, "group_by": True, "http_stateless": True,
                       "btree_index": False, "fk_unique": True, "git_scale": 5},
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 4, "confidence_deadline": 5,
                       "tools": [1, 3], "autonomy": "yes"},
    },
    {
        "username": "yanis.belkacem", "first_name": "Yanis", "last_name": "Belkacem",
        "birth_date": "1998-07-22",
        "video": "sintel",
        "headline": "Développeur fullstack JavaScript",
        "summary": "Passionné par les interfaces réactives et les architectures Node.js. "
                    "À l'aise aussi bien côté client que côté serveur.",
        "city": "Lyon", "field": pc.FIELD_SOFTWARE,
        "availability": pc.AVAILABILITY_OPEN_TO_OPPORTUNITIES, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_remote": True},
        "skills": [
            ("JavaScript", pc.LEVEL_EXPERT, 5), ("React", pc.LEVEL_ADVANCED, 4),
            ("Node.js", pc.LEVEL_ADVANCED, 4), ("TypeScript", pc.LEVEL_INTERMEDIATE, 2),
            ("MongoDB", pc.LEVEL_INTERMEDIATE, 2),
        ],
        "experiences": [
            {"title": "Développeur fullstack", "company": "BlaBlaCar", "start": "2022-01-01",
             "current": True, "skills": ["React", "Node.js", "TypeScript"],
             "description": "Équipe covoiturage longue distance, du back-office au front public."},
            {"title": "Développeur front-end", "company": "Wexperience", "start": "2020-06-01",
             "end": "2021-12-31", "skills": ["JavaScript", "React"]},
        ],
        "education": [
            {"institution": "42 Paris", "degree": "Titre RNCP développeur web",
             "level": pc.DEGREE_BAC_3, "start": "2018-09-01", "end": "2020-06-30"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B2), ("ar", pc.CEFR_B1)],
        "projects": [
            {"title": "Plateforme de covoiturage étudiant", "role": "Créateur", "skills": ["React", "Node.js"],
             "description": "Projet personnel lancé pour le campus de Lyon 2, environ 300 utilisateurs actifs."},
        ],
        "links": [("GITHUB", "https://github.com/yanisbelkacem")],
        "q1_answers": {"http_201": True, "db_relational": ["PostgreSQL", "MySQL", "MongoDB"], "get_idempotent": "no",
                       "json_format": True, "group_by": True, "http_stateless": True,
                       "btree_index": False, "fk_unique": False, "git_scale": 4},
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": False, "confidence_talk": 3, "confidence_deadline": 4,
                       "tools": [0, 2], "autonomy": "yes"},
    },
    {
        "username": "lea.girard", "first_name": "Léa", "last_name": "Girard",
        "birth_date": "1995-11-03",
        "headline": "Data analyst",
        "summary": "J'aide les équipes métier à prendre des décisions à partir de données fiables. "
                    "Spécialisée dans la logistique et le retail.",
        "city": "Bordeaux", "field": pc.FIELD_DATA,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_hybrid": True},
        "skills": [
            ("SQL", pc.LEVEL_EXPERT, 4), ("Python", pc.LEVEL_ADVANCED, 4),
            ("Power BI", pc.LEVEL_ADVANCED, 3), ("Excel", pc.LEVEL_EXPERT, 6),
            ("Statistiques", pc.LEVEL_INTERMEDIATE, 3),
        ],
        "experiences": [
            {"title": "Data analyst", "company": "Cdiscount", "start": "2021-05-01",
             "current": True, "skills": ["SQL", "Power BI"],
             "description": "Suivi de la performance logistique et des délais de livraison."},
            {"title": "Analyste business intelligence", "company": "Groupe La Poste", "start": "2019-01-01",
             "end": "2021-04-30", "skills": ["SQL", "Excel"]},
        ],
        "education": [
            {"institution": "Université de Bordeaux", "degree": "Master MIAGE",
             "level": pc.DEGREE_BAC_5, "start": "2017-09-01", "end": "2019-06-30"},
        ],
        "certifications": [
            {"name": "Google Data Analytics Certificate", "issuer": "Google", "issued": "2022-09-01"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B2), ("es", pc.CEFR_A2)],
        "projects": [
            {"title": "Tableau de bord logistique temps réel", "role": "Autrice", "skills": ["Power BI", "SQL"]},
        ],
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 3, "confidence_deadline": 5,
                       "tools": [1, 4], "autonomy": "yes"},
    },
    {
        "username": "thomas.perrin", "first_name": "Thomas", "last_name": "Perrin",
        "birth_date": "1993-02-17",
        "headline": "Ingénieur DevOps",
        "summary": "Dix ans dans l'industrialisation des déploiements. Terrain de jeu favori : "
                    "Kubernetes et l'infrastructure as code.",
        "city": "Toulouse", "field": pc.FIELD_INFRASTRUCTURE,
        "availability": pc.AVAILABILITY_CURRENTLY_EMPLOYED, "contracts": [],
        "work_modes": {"open_to_hybrid": True},
        "skills": [
            ("Kubernetes", pc.LEVEL_EXPERT, 4), ("Docker", pc.LEVEL_EXPERT, 5),
            ("Terraform", pc.LEVEL_ADVANCED, 3), ("AWS", pc.LEVEL_ADVANCED, 4),
            ("Linux", pc.LEVEL_EXPERT, 8),
        ],
        "experiences": [
            {"title": "Ingénieur DevOps", "company": "Airbus", "start": "2020-02-01",
             "current": True, "skills": ["Kubernetes", "Terraform", "AWS"],
             "description": "Plateforme interne de déploiement continu pour les équipes logicielles."},
            {"title": "Administrateur systèmes", "company": "CGI", "start": "2016-09-01",
             "end": "2020-01-31", "skills": ["Linux", "Docker"]},
        ],
        "education": [
            {"institution": "INSA Toulouse", "degree": "Diplôme d'ingénieur",
             "level": pc.DEGREE_BAC_5, "start": "2011-09-01", "end": "2016-06-30"},
        ],
        "certifications": [
            {"name": "AWS Certified Solutions Architect – Associate", "issuer": "Amazon Web Services",
             "issued": "2023-02-01"},
            {"name": "Certified Kubernetes Administrator", "issuer": "Cloud Native Computing Foundation",
             "issued": "2022-05-01"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_C1)],
        "projects": [
            {"title": "Migration on-premise vers AWS", "role": "Pilote technique",
             "skills": ["AWS", "Terraform"], "description": "Migration de 40 services en six mois, zéro interruption."},
        ],
        "q1_answers": {"http_201": True, "db_relational": ["PostgreSQL", "MySQL", "SQLite"], "get_idempotent": "no",
                       "json_format": True, "group_by": False, "http_stateless": True,
                       "btree_index": True, "fk_unique": False, "git_scale": 4},
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": False,
                       "blockers_tf": True, "confidence_talk": 3, "confidence_deadline": 4,
                       "tools": [2, 3], "autonomy": "yes"},
    },
    {
        "username": "ines.moreau", "first_name": "Inès", "last_name": "Moreau",
        "birth_date": "1997-09-30",
        "headline": "UX/UI Designer",
        "summary": "Je conçois des interfaces utiles avant d'être belles. Forte appétence pour "
                    "la recherche utilisateur et les design systems.",
        "city": "Rennes", "field": pc.FIELD_DESIGN,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_FREELANCE, pc.CONTRACT_CDI],
        "work_modes": {"open_to_remote": True},
        "skills": [
            ("Figma", pc.LEVEL_EXPERT, 5), ("UX Research", pc.LEVEL_ADVANCED, 4),
            ("Design System", pc.LEVEL_ADVANCED, 3), ("Prototypage", pc.LEVEL_EXPERT, 5),
            ("Adobe XD", pc.LEVEL_INTERMEDIATE, 3),
        ],
        "experiences": [
            {"title": "UX/UI Designer", "company": "Ouest-France", "start": "2021-04-01",
             "current": True, "skills": ["Figma", "UX Research"],
             "description": "Refonte de l'expérience de lecture sur l'application mobile."},
            {"title": "Designer produit junior", "company": "Fabernovel", "start": "2019-09-01",
             "end": "2021-03-31", "skills": ["Adobe XD"]},
        ],
        "education": [
            {"institution": "École de Design Nantes Atlantique", "degree": "Bachelor Design",
             "level": pc.DEGREE_BAC_3, "start": "2016-09-01", "end": "2019-06-30"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B2)],
        "projects": [
            {"title": "Refonte de l'app mobile Ouest-France", "role": "Lead designer",
             "skills": ["Figma", "UX Research"]},
            {"title": "Design system pour une fintech", "role": "Freelance", "skills": ["Design System"]},
        ],
        "links": [("PORTFOLIO", "https://inesmoreau.design"), ("BEHANCE", "https://behance.net/inesmoreau")],
        "video": "sintel",
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 5, "confidence_deadline": 4,
                       "tools": [0, 1, 3], "autonomy": "yes"},
    },
    {
        "username": "nathan.roche", "first_name": "Nathan", "last_name": "Roche",
        "birth_date": "1995-06-14",
        "headline": "Chef de projet marketing digital",
        "summary": "J'orchestre des campagnes multicanales, du brief à l'analyse de performance.",
        "city": "Lille", "field": pc.FIELD_MARKETING,
        "availability": pc.AVAILABILITY_OPEN_TO_OPPORTUNITIES, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_hybrid": True},
        "skills": [
            ("SEO", pc.LEVEL_ADVANCED, 4), ("Google Ads", pc.LEVEL_EXPERT, 5),
            ("Google Analytics", pc.LEVEL_ADVANCED, 4), ("Content Marketing", pc.LEVEL_INTERMEDIATE, 3),
            ("CRM", pc.LEVEL_INTERMEDIATE, 2),
        ],
        "experiences": [
            {"title": "Chargé de marketing digital", "company": "Decathlon", "start": "2020-03-01",
             "current": True, "skills": ["Google Ads", "SEO"],
             "description": "Pilotage des campagnes d'acquisition pour l'e-commerce France."},
            {"title": "Assistant marketing", "company": "iProspect", "start": "2018-09-01",
             "end": "2020-02-28", "skills": ["Google Analytics"]},
        ],
        "education": [
            {"institution": "IÉSEG School of Management", "degree": "Master marketing",
             "level": pc.DEGREE_BAC_5, "start": "2016-09-01", "end": "2018-06-30"},
        ],
        "certifications": [
            {"name": "Google Ads Search Certification", "issuer": "Google", "issued": "2023-01-01"},
            {"name": "HubSpot Content Marketing", "issuer": "HubSpot Academy", "issued": "2022-06-01"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B2), ("nl", pc.CEFR_A2)],
        "projects": [
            {"title": "Campagne de lancement produit multicanale", "role": "Chef de projet",
             "skills": ["Google Ads", "Content Marketing"]},
        ],
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 5, "confidence_deadline": 4,
                       "tools": [1, 4, 5], "autonomy": "yes"},
    },
    {
        "username": "sarah.benali", "first_name": "Sarah", "last_name": "Benali",
        "birth_date": "1999-12-05",
        "video": "elephants_dream",
        "headline": "Développeuse mobile iOS/Android",
        "summary": "Je construis des applications mobiles fluides, du prototype au déploiement en store.",
        "city": "Marseille", "field": pc.FIELD_SOFTWARE,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_CDD, pc.CONTRACT_CDI],
        "work_modes": {"open_to_remote": True, "open_to_onsite": True},
        "skills": [
            ("Swift", pc.LEVEL_ADVANCED, 4), ("Kotlin", pc.LEVEL_INTERMEDIATE, 2),
            ("Flutter", pc.LEVEL_ADVANCED, 3), ("Firebase", pc.LEVEL_INTERMEDIATE, 2),
            ("Git", pc.LEVEL_ADVANCED, 4),
        ],
        "experiences": [
            {"title": "Développeuse mobile", "company": "Tiller", "start": "2021-06-01",
             "current": True, "skills": ["Flutter", "Firebase"],
             "description": "Application de caisse pour commerçants indépendants."},
            {"title": "Développeuse junior", "company": "SNCF Connect", "start": "2020-09-01",
             "end": "2021-05-31", "skills": ["Swift"]},
        ],
        "education": [
            {"institution": "Epitech Marseille", "degree": "Bachelor informatique",
             "level": pc.DEGREE_BAC_3, "start": "2017-09-01", "end": "2020-06-30"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("ar", pc.CEFR_NATIVE), ("en", pc.CEFR_B1)],
        "projects": [
            {"title": "Application de covoiturage local", "role": "Créatrice", "skills": ["Flutter"]},
        ],
        "q1_answers": {"http_201": True, "db_relational": ["PostgreSQL", "MongoDB"], "get_idempotent": "yes",
                       "json_format": True, "group_by": False, "http_stateless": False,
                       "btree_index": False, "fk_unique": False, "git_scale": 3},
        "q2_answers": {"scenario_error": True, "delay_tf": False, "scenario_angry": False,
                       "blockers_tf": True, "confidence_talk": 3, "confidence_deadline": 3,
                       "tools": [0, 2], "autonomy": "no"},
    },
    {
        "username": "hugo.faure", "first_name": "Hugo", "last_name": "Faure",
        "birth_date": "1994-08-19",
        "headline": "Business Developer B2B",
        "summary": "Sept ans en développement commercial, du premier rendez-vous à la signature.",
        "city": "Strasbourg", "field": pc.FIELD_SALES,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_onsite": True, "open_to_hybrid": True},
        "skills": [
            ("Négociation", pc.LEVEL_EXPERT, 6), ("Prospection", pc.LEVEL_ADVANCED, 5),
            ("Salesforce", pc.LEVEL_INTERMEDIATE, 3), ("Closing", pc.LEVEL_ADVANCED, 4),
        ],
        "experiences": [
            {"title": "Business Developer", "company": "Alan", "start": "2021-01-01",
             "current": True, "skills": ["Négociation", "Salesforce"],
             "description": "Développement du portefeuille PME dans le Grand Est."},
            {"title": "Commercial terrain", "company": "Michelin", "start": "2017-09-01",
             "end": "2020-12-31", "skills": ["Prospection"]},
        ],
        "education": [
            {"institution": "EM Strasbourg", "degree": "Master commerce",
             "level": pc.DEGREE_BAC_5, "start": "2015-09-01", "end": "2017-06-30"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B1), ("de", pc.CEFR_B1)],
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 5, "confidence_deadline": 4,
                       "tools": [1, 3], "autonomy": "yes"},
    },
    {
        "username": "chloe.lefevre", "first_name": "Chloé", "last_name": "Lefèvre",
        "birth_date": "1997-01-27",
        "headline": "Data scientist",
        "summary": "Je conçois des modèles qui passent réellement en production, pas seulement "
                    "dans un notebook.",
        "city": "Paris", "field": pc.FIELD_DATA,
        "availability": pc.AVAILABILITY_OPEN_TO_OPPORTUNITIES, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_hybrid": True, "open_to_remote": True},
        "skills": [
            ("Python", pc.LEVEL_EXPERT, 5), ("Machine Learning", pc.LEVEL_ADVANCED, 4),
            ("TensorFlow", pc.LEVEL_INTERMEDIATE, 2), ("SQL", pc.LEVEL_ADVANCED, 4),
            ("Pandas", pc.LEVEL_EXPERT, 4),
        ],
        "experiences": [
            {"title": "Data scientist", "company": "Deezer", "start": "2022-03-01",
             "current": True, "skills": ["Python", "Machine Learning", "TensorFlow"],
             "description": "Modèles de recommandation pour la page d'accueil."},
            {"title": "Data analyst", "company": "Ubisoft", "start": "2020-09-01",
             "end": "2022-02-28", "skills": ["SQL", "Pandas"]},
        ],
        "education": [
            {"institution": "Sorbonne Université", "degree": "Master Data Science",
             "level": pc.DEGREE_BAC_5, "start": "2018-09-01", "end": "2020-06-30"},
            {"institution": "Lycée Louis-le-Grand", "degree": "Classe préparatoire MPSI/MP",
             "level": pc.DEGREE_BAC_2, "start": "2016-09-01", "end": "2018-06-30"},
        ],
        "certifications": [
            {"name": "TensorFlow Developer Certificate", "issuer": "Google", "issued": "2023-05-01"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_C1)],
        "projects": [
            {"title": "Modèle de recommandation musicale", "role": "Autrice", "skills": ["TensorFlow", "Python"]},
            {"title": "Détection de churn utilisateurs", "role": "Autrice", "skills": ["Machine Learning", "SQL"]},
        ],
        "q1_answers": {"http_201": False, "db_relational": ["PostgreSQL", "MySQL", "SQLite"], "get_idempotent": "yes",
                       "json_format": True, "group_by": True, "http_stateless": True,
                       "btree_index": False, "fk_unique": True, "git_scale": 3},
        "q2_answers": {"scenario_error": False, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 3, "confidence_deadline": 5,
                       "tools": [0, 4], "autonomy": "yes"},
    },
    {
        "username": "maxime.girard", "first_name": "Maxime", "last_name": "Girard",
        "birth_date": "1994-05-09",
        "headline": "Développeur backend Java",
        "summary": "Sept ans sur des systèmes bancaires critiques. Rigueur et couverture de tests "
                    "avant tout.",
        "city": "Montpellier", "field": pc.FIELD_SOFTWARE,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_hybrid": True},
        "skills": [
            ("Java", pc.LEVEL_EXPERT, 7), ("Spring Boot", pc.LEVEL_ADVANCED, 5),
            ("PostgreSQL", pc.LEVEL_ADVANCED, 5), ("Docker", pc.LEVEL_INTERMEDIATE, 2),
            ("Kafka", pc.LEVEL_BEGINNER, 1),
        ],
        "experiences": [
            {"title": "Développeur backend Java", "company": "Sopra Steria", "start": "2019-04-01",
             "current": True, "skills": ["Java", "Spring Boot", "PostgreSQL"],
             "description": "Refonte des microservices de traitement des virements pour un grand groupe bancaire."},
            {"title": "Développeur junior", "company": "Capgemini", "start": "2017-09-01",
             "end": "2019-03-31", "skills": ["Java"]},
        ],
        "education": [
            {"institution": "Polytech Montpellier", "degree": "Diplôme d'ingénieur",
             "level": pc.DEGREE_BAC_5, "start": "2012-09-01", "end": "2017-06-30"},
        ],
        "certifications": [
            {"name": "Oracle Certified Professional Java SE 11", "issuer": "Oracle", "issued": "2021-03-01"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B2)],
        "projects": [
            {"title": "Refonte microservices d'une plateforme bancaire", "role": "Développeur référent",
             "skills": ["Java", "Spring Boot", "Kafka"]},
        ],
        "q1_answers": {"http_201": True, "db_relational": ["PostgreSQL", "MySQL", "SQLite"], "get_idempotent": "no",
                       "json_format": True, "group_by": True, "http_stateless": True,
                       "btree_index": True, "fk_unique": False, "git_scale": 5},
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 4, "confidence_deadline": 5,
                       "tools": [1, 3, 4], "autonomy": "yes"},
    },
    {
        "username": "manon.roussel", "first_name": "Manon", "last_name": "Roussel",
        "birth_date": "1997-03-16",
        "headline": "Chargée de recrutement",
        "summary": "Spécialisée dans le recrutement technique et l'expérience candidat.",
        "city": "Nice", "field": pc.FIELD_HR,
        "availability": pc.AVAILABILITY_OPEN_TO_OPPORTUNITIES, "contracts": [pc.CONTRACT_CDI],
        "work_modes": {"open_to_hybrid": True},
        "skills": [
            ("Recrutement", pc.LEVEL_EXPERT, 6), ("Entretien", pc.LEVEL_ADVANCED, 5),
            ("SIRH", pc.LEVEL_INTERMEDIATE, 3), ("Droit du travail", pc.LEVEL_INTERMEDIATE, 3),
        ],
        "experiences": [
            {"title": "Chargée de recrutement", "company": "Thales", "start": "2020-01-01",
             "current": True, "skills": ["Recrutement", "Entretien"],
             "description": "Recrutement des profils ingénieurs pour la division systèmes navals."},
            {"title": "Assistante RH", "company": "Randstad", "start": "2018-03-01",
             "end": "2019-12-31", "skills": ["SIRH"]},
        ],
        "education": [
            {"institution": "Université Nice Sophia Antipolis", "degree": "Licence RH",
             "level": pc.DEGREE_BAC_3, "start": "2015-09-01", "end": "2018-06-30"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B1), ("it", pc.CEFR_A2)],
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": True, "confidence_talk": 5, "confidence_deadline": 4,
                       "tools": [1, 3], "autonomy": "yes"},
    },
    {
        "username": "adam.kacimi", "first_name": "Adam", "last_name": "Kacimi",
        "birth_date": "1996-10-08",
        "headline": "Ingénieur QA / testeur logiciel",
        "summary": "J'automatise ce qui peut l'être et je traque les régressions avant les utilisateurs.",
        "city": "Grenoble", "field": pc.FIELD_SOFTWARE,
        "availability": pc.AVAILABILITY_OPEN_TO_WORK, "contracts": [pc.CONTRACT_CDD, pc.CONTRACT_CDI],
        "work_modes": {"open_to_remote": True},
        "skills": [
            ("Selenium", pc.LEVEL_ADVANCED, 3), ("Cypress", pc.LEVEL_INTERMEDIATE, 2),
            ("Test unitaire", pc.LEVEL_ADVANCED, 4), ("CI/CD", pc.LEVEL_INTERMEDIATE, 2),
            ("Python", pc.LEVEL_INTERMEDIATE, 2),
        ],
        "experiences": [
            {"title": "Ingénieur QA", "company": "STMicroelectronics", "start": "2021-09-01",
             "current": True, "skills": ["Selenium", "CI/CD"],
             "description": "Automatisation des tests de non-régression sur les outils de conception."},
            {"title": "Testeur logiciel", "company": "Atos", "start": "2019-09-01",
             "end": "2021-08-31", "skills": ["Test unitaire"]},
        ],
        "education": [
            {"institution": "Grenoble INP - Ensimag", "degree": "Diplôme d'ingénieur",
             "level": pc.DEGREE_BAC_5, "start": "2014-09-01", "end": "2019-06-30"},
        ],
        "languages": [("fr", pc.CEFR_NATIVE), ("en", pc.CEFR_B2)],
        "video": "tears_of_steel",
        "q1_answers": {"http_201": True, "db_relational": ["PostgreSQL", "MySQL", "SQLite"], "get_idempotent": "no",
                       "json_format": True, "group_by": True, "http_stateless": True,
                       "btree_index": False, "fk_unique": False, "git_scale": 4},
        "q2_answers": {"scenario_error": True, "delay_tf": True, "scenario_angry": True,
                       "blockers_tf": False, "confidence_talk": 3, "confidence_deadline": 4,
                       "tools": [2, 3], "autonomy": "yes"},
    },
]

DB_OPTIONS = ["PostgreSQL", "MongoDB", "MySQL", "Redis", "SQLite"]
TOOLS_OPTIONS = ["Notion", "Trello", "Slack", "Jira", "Google Calendar", "Asana"]

class Command(BaseCommand):
    help = "Peuple la base avec un jeu de donnees de demonstration credible."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._reset()
            admin = self._create_admin()
            self._create_recruiters()
            candidates = self._create_candidates()
            q1, q2 = self._create_questionnaires(admin)
            self._seed_profiles(candidates)
            self._seed_attempts(candidates, q1, q2)
            self._seed_mainapp_feed(candidates)

        self._summary(candidates)

    def _reset(self):
        usernames = (
            [c["username"] for c in CANDIDATES]
            + [r["username"] for r in RECRUITERS]
            + [ADMIN_ACCOUNT["username"]]
        )
        deleted, _ = User.objects.filter(username__in = usernames).delete()
        Questionnaire.objects.filter(
            title__in = ["Test technique — Backend", "Évaluation — Communication & organisation"]
        ).delete()
        if deleted:
            self.stdout.write(f"Anciennes donnees de demonstration supprimees ({deleted} lignes).")

    def _create_admin(self) -> User:
        user = User.objects.create_user(
            ADMIN_ACCOUNT["username"], None, DEMO_PASSWORD,
            first_name = ADMIN_ACCOUNT["first_name"], last_name = ADMIN_ACCOUNT["last_name"],
            is_staff = True, is_superuser = True,
        )
        Role.objects.create(user = user, role = "Admin", birth_date = ADMIN_ACCOUNT["birth_date"])
        return user

    def _create_recruiters(self) -> list:
        users = []
        for data in RECRUITERS:
            user = User.objects.create_user(
                data["username"], None, DEMO_PASSWORD,
                first_name = data["first_name"], last_name = data["last_name"],
            )
            Role.objects.create(user = user, role = "Recruiter", birth_date = data["birth_date"])
            users.append(user)
        return users

    def _create_candidates(self) -> list:
        users = []
        for data in CANDIDATES:
            user = User.objects.create_user(
                data["username"], None, DEMO_PASSWORD,
                first_name = data["first_name"], last_name = data["last_name"],
            )
            Role.objects.create(user = user, role = "JobSeeker", birth_date = data["birth_date"])
            users.append(user)
        return users

    def _seed_profiles(self, users: list):
        for user, data in zip(users, CANDIDATES):
            profile = profile_services.get_profile(user)
            profile_services.update_profile(profile, {
                "headline": data["headline"], "summary": data["summary"],
                "location_city": data["city"], "location_country": "FR",
                "professional_field": data["field"],
                "availability_status": data["availability"],
                "contract_types": data["contracts"],
                **data.get("work_modes", {}),
                "visibility": pc.VISIBILITY_PUBLIC,
            })
            profile_services.update_search_settings(profile, {"searchable": True})

            for name, level, years in data["skills"]:
                profile_services.add_skill(profile, {"name": name, "level": level, "years_experience": years})

            for exp in data["experiences"]:
                profile_services.create_experience(profile, {
                    "title": exp["title"], "company": exp["company"],
                    "start_date": exp["start"], "end_date": exp.get("end"),
                    "is_current": exp.get("current", False),
                    "description": exp.get("description", ""),
                    "skills": exp.get("skills", []),
                })

            for edu in data.get("education", []):
                profile_services.create_education(profile, {
                    "institution": edu["institution"], "degree": edu["degree"],
                    "degree_level": edu["level"], "start_date": edu["start"], "end_date": edu["end"],
                })

            for cert in data.get("certifications", []):
                profile_services.create_certification(profile, {
                    "name": cert["name"], "issuer": cert["issuer"], "issued_on": cert["issued"],
                })

            for code, level in data.get("languages", []):
                profile_services.set_language(profile, {"language": code, "level": level})

            for project in data.get("projects", []):
                profile_services.create_project(profile, {
                    "title": project["title"], "role": project.get("role", ""),
                    "description": project.get("description", ""), "skills": project.get("skills", []),
                })

            if data.get("links"):
                profile_services.set_links(profile, [
                    {"kind": kind, "url": url} for kind, url in data["links"]
                ])

            if data.get("video"):
                profile_services.create_video(profile, {
                    "title": f"{data['first_name']} se présente",
                    "description": f"Courte présentation de {data['first_name']} et de son parcours.",
                    "file_url": DEMO_CLIPS[data["video"]],
                    "thumbnail_url": "", "status": pc.VIDEO_PUBLISHED,
                    "skills": [s[0] for s in data["skills"][:3]],
                })

    def _create_questionnaires(self, admin: User):
        q1 = self._build_backend_test(admin)
        q2 = self._build_soft_skills(admin)
        return q1, q2

    def _publish(self, title: str, description: str, admin: User, build_questions):
        questionnaire = Questionnaire.objects.create(title = title, description = description, created_by = admin)
        version = create_version(questionnaire, source = None, actor = admin, title = title)
        keys = build_questions(version, admin)
        publish_version(version, actor = admin)
        return questionnaire, keys

    def _build_backend_test(self, admin: User):
        def build(version, admin):
            keys = {}
            keys["http_201"] = create_question(version, {
                "type": qc.TYPE_SINGLE_CHOICE,
                "text": "Quel code HTTP indique qu'une ressource a été créée avec succès ?",
                "options": [
                    {"text": "200 OK"}, {"text": "201 Created", "is_correct": True},
                    {"text": "204 No Content"}, {"text": "400 Bad Request"},
                ],
            }, actor = admin)
            keys["db_relational"] = create_question(version, {
                "type": qc.TYPE_MULTIPLE_CHOICE,
                "text": "Parmi ces systèmes de stockage, lesquels sont des bases de données relationnelles ?",
                "options": [{"text": name, "is_correct": name in ("PostgreSQL", "MySQL", "SQLite")}
                           for name in DB_OPTIONS],
            }, actor = admin)
            keys["get_idempotent"] = create_question(version, {
                "type": qc.TYPE_YES_NO,
                "text": "Une requête GET doit-elle pouvoir provoquer un effet de bord durable sur le serveur ?",
            }, actor = admin)
            update_question(keys["get_idempotent"], {
                "options": [{"text": "Oui", "value": "yes", "is_correct": False},
                           {"text": "Non", "value": "no", "is_correct": True}],
            })
            keys["json_format"] = create_question(version, {
                "type": qc.TYPE_DROPDOWN,
                "text": "Quel format est aujourd'hui le plus utilisé pour les API REST ?",
                "options": [{"text": "XML"}, {"text": "JSON", "is_correct": True},
                           {"text": "CSV"}, {"text": "YAML"}],
            }, actor = admin)
            keys["group_by"] = create_question(version, {
                "type": qc.TYPE_SINGLE_CHOICE,
                "text": "Que fait la clause SQL `GROUP BY` ?",
                "options": [
                    {"text": "Elle trie les résultats"}, {"text": "Elle filtre les lignes"},
                    {"text": "Elle regroupe les lignes partageant une même valeur", "is_correct": True},
                    {"text": "Elle supprime les doublons"},
                ],
            }, actor = admin)
            keys["http_stateless"] = create_question(version, {
                "type": qc.TYPE_TRUE_FALSE,
                "text": "Le protocole HTTP est, par nature, un protocole avec état (stateful).",
            }, actor = admin)
            update_question(keys["http_stateless"], {
                "options": [{"text": "Vrai", "value": "true", "is_correct": False},
                           {"text": "Faux", "value": "false", "is_correct": True}],
            })
            keys["btree_index"] = create_question(version, {
                "type": qc.TYPE_SINGLE_CHOICE,
                "text": "Quel type d'index accélère le plus une recherche par égalité sur une colonne "
                        "à forte cardinalité ?",
                "options": [
                    {"text": "Aucun index n'est nécessaire"}, {"text": "Un index B-Tree", "is_correct": True},
                    {"text": "Un index plein texte"}, {"text": "Une vue matérialisée"},
                ],
            }, actor = admin)
            keys["fk_unique"] = create_question(version, {
                "type": qc.TYPE_TRUE_FALSE,
                "text": "Une clé étrangère peut référencer une colonne qui n'est pas une clé primaire "
                        "dans la table cible, tant qu'elle est contrainte par une clé unique.",
            }, actor = admin)
            update_question(keys["fk_unique"], {
                "options": [{"text": "Vrai", "value": "true", "is_correct": True},
                           {"text": "Faux", "value": "false", "is_correct": False}],
            })
            keys["git_scale"] = create_question(version, {
                "type": qc.TYPE_SCALE, "required": False,
                "text": "Sur une échelle de 1 à 5, votre niveau de confort avec Git et les workflows de branches ?",
                "config": {"min": 1, "max": 5, "step": 1},
            }, actor = admin)
            return keys

        questionnaire, keys = self._publish(
            "Test technique — Backend",
            "Fondamentaux HTTP, bases de données et bonnes pratiques d'API.",
            admin, build,
        )
        return {"questionnaire": questionnaire, "keys": keys}

    def _build_soft_skills(self, admin: User):
        def build(version, admin):
            keys = {}
            keys["scenario_error"] = create_question(version, {
                "type": qc.TYPE_SINGLE_CHOICE,
                "text": "Un collègue vous signale une erreur dans un livrable déjà transmis au client. "
                        "Quelle est votre priorité ?",
                "options": [
                    {"text": "Ignorer, ce n'est pas grave"},
                    {"text": "Corriger et prévenir le client avant qu'il ne le remarque", "is_correct": True},
                    {"text": "Attendre que le client s'en aperçoive"},
                    {"text": "Reporter la faute sur un autre membre de l'équipe"},
                ],
            }, actor = admin)
            keys["delay_tf"] = create_question(version, {
                "type": qc.TYPE_TRUE_FALSE,
                "text": "Il vaut mieux communiquer un retard dès qu'il est identifié plutôt qu'au dernier moment.",
            }, actor = admin)
            update_question(keys["delay_tf"], {
                "options": [{"text": "Vrai", "value": "true", "is_correct": True},
                           {"text": "Faux", "value": "false", "is_correct": False}],
            })
            keys["scenario_angry"] = create_question(version, {
                "type": qc.TYPE_SINGLE_CHOICE,
                "text": "Vous recevez un message d'un client mécontent en fin de journée. "
                        "Quelle est la meilleure première réaction ?",
                "options": [
                    {"text": "Répondre immédiatement, avec de l'humeur"},
                    {"text": "Ne pas répondre et attendre le lendemain sans prévenir"},
                    {"text": "Accuser réception rapidement et proposer un échange le lendemain matin",
                     "is_correct": True},
                    {"text": "Transférer le message à un collègue sans commentaire"},
                ],
            }, actor = admin)
            keys["blockers_tf"] = create_question(version, {
                "type": qc.TYPE_TRUE_FALSE,
                "text": "Dans un travail d'équipe, il vaut mieux garder ses blocages pour soi jusqu'à "
                        "ce qu'ils soient résolus.",
            }, actor = admin)
            update_question(keys["blockers_tf"], {
                "options": [{"text": "Vrai", "value": "true", "is_correct": False},
                           {"text": "Faux", "value": "false", "is_correct": True}],
            })
            keys["confidence_talk"] = create_question(version, {
                "type": qc.TYPE_SCALE, "required": False,
                "text": "Sur une échelle de 1 à 5, votre aisance à l'oral devant un groupe ?",
                "config": {"min": 1, "max": 5, "step": 1},
            }, actor = admin)
            keys["confidence_deadline"] = create_question(version, {
                "type": qc.TYPE_SCALE, "required": False,
                "text": "Sur une échelle de 1 à 5, votre capacité à respecter les délais annoncés ?",
                "config": {"min": 1, "max": 5, "step": 1},
            }, actor = admin)
            keys["tools"] = create_question(version, {
                "type": qc.TYPE_MULTI_SELECT, "required": False,
                "text": "Quels outils utilisez-vous pour organiser votre travail au quotidien ?",
                "options": [{"text": name} for name in TOOLS_OPTIONS],
            }, actor = admin)
            keys["autonomy"] = create_question(version, {
                "type": qc.TYPE_YES_NO, "required": False,
                "text": "Êtes-vous à l'aise pour travailler en autonomie sur un projet peu cadré ?",
            }, actor = admin)
            return keys

        questionnaire, keys = self._publish(
            "Évaluation — Communication & organisation",
            "Mises en situation et auto-évaluation, pour cerner la manière de travailler d'un candidat.",
            admin, build,
        )
        return {"questionnaire": questionnaire, "keys": keys}

    def _seed_attempts(self, users: list, q1: dict, q2: dict):
        for user, data in zip(users, CANDIDATES):
            if "q1_answers" in data:
                self._run_attempt(user, q1, data["q1_answers"], {
                    "http_201":      lambda opts, v: opts[0].id if not v else opts[1].id,
                    "db_relational": self._db_relational_value,
                    "get_idempotent": lambda opts, v: next(o.id for o in opts if o.value == v),
                    "json_format":   lambda opts, v: opts[1].id if v else opts[0].id,
                    "group_by":      lambda opts, v: opts[2].id if v else opts[0].id,
                    "http_stateless": lambda opts, v: next(o.id for o in opts if (o.value == "false") == v),
                    "btree_index":   lambda opts, v: opts[1].id if v else opts[0].id,
                    "fk_unique":     lambda opts, v: next(o.id for o in opts if (o.value == "true") == v),
                    "git_scale":     lambda opts, v: next(o.id for o in opts if o.value == str(v)),
                })
            if "q2_answers" in data:
                self._run_attempt(user, q2, data["q2_answers"], {
                    "scenario_error":  lambda opts, v: opts[1].id if v else opts[0].id,
                    "delay_tf":        lambda opts, v: next(o.id for o in opts if (o.value == "true") == v),
                    "scenario_angry":  lambda opts, v: opts[2].id if v else opts[0].id,
                    "blockers_tf":     lambda opts, v: next(o.id for o in opts if (o.value == "false") == v),
                    "confidence_talk": lambda opts, v: next(o.id for o in opts if o.value == str(v)),
                    "confidence_deadline": lambda opts, v: next(o.id for o in opts if o.value == str(v)),
                    "tools":           lambda opts, v: [opts[i].id for i in v],
                    "autonomy":        lambda opts, v: next(o.id for o in opts if o.value == v),
                })

    def _db_relational_value(self, opts, selected_names):
        return [opt.id for opt in opts if opt.text in selected_names]

    def _run_attempt(self, user, questionnaire_data: dict, answers: dict, resolvers: dict):
        questionnaire = questionnaire_data["questionnaire"]
        attempt = attempt_services.start_attempt(questionnaire, user)
        for key, question in questionnaire_data["keys"].items():
            if key not in answers:
                continue
            options = list(question.options.all())
            value = resolvers[key](options, answers[key])
            attempt_services.save_answer(attempt, question.id, value)
        attempt_services.finish_attempt(attempt)

    def _seed_mainapp_feed(self, candidates: list):
        """Reactions des recruteurs sur les videos publiees du feed.

        Le feed est servi par `profiles.ProfileVideo` (pile video unifiee) :
        les recruteurs de demonstration reagissent directement dessus, pour
        que les compteurs ne soient pas tous a zero a la premiere ouverture.
        """
        from profils.profiles import engagement
        from profils.profiles.models import ProfileVideo

        recruiters = list(User.objects.filter(username__in = [r["username"] for r in RECRUITERS]))
        reaction_cycle = ["like", "like", "dislike", "like", "like"]

        published = (
            ProfileVideo.objects
            .filter(status = pc.VIDEO_PUBLISHED)
            .select_related("profile__user")
            .order_by("id")
        )
        for index, video in enumerate(published):
            for offset, recruiter in enumerate(recruiters):
                engagement.set_reaction(
                    video, recruiter, reaction_cycle[(index + offset) % len(reaction_cycle)],
                )
                engagement.register_view(video, user = recruiter)

    def _summary(self, candidates: list):
        self.stdout.write(self.style.SUCCESS(
            f"\nDonnees de demonstration en place : {len(candidates)} candidats, "
            f"{len(RECRUITERS)} recruteurs, 1 compte administrateur.\n"
            f"Mot de passe pour tous les comptes : {DEMO_PASSWORD}\n"
            f"Exemples : {CANDIDATES[0]['username']}  ·  {RECRUITERS[0]['username']}  ·  "
            f"{ADMIN_ACCOUNT['username']}"
        ))
