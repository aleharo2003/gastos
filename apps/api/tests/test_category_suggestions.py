import unittest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.category_suggestions import suggest_category, EMPTY
from app.expenses import router


class SuggestionTests(unittest.TestCase):
    @staticmethod
    def rows(*categories, description='Cerveza'):
        return [{'descripcion':description,'categoria':category} for category in categories]

    def test_requires_two_categorized_examples(self):
        for rows in [[],self.rows('alimentos'),self.rows(None,None)]:
            self.assertEqual(suggest_category('cerveza',rows),EMPTY)
        self.assertEqual(suggest_category('cerveza',self.rows('alimentos','alimentos')),
                         {'categoria':'alimentos','coincidencias':2,'total':2})

    def test_ambiguity_and_dominance(self):
        self.assertEqual(suggest_category('cerveza',self.rows('ocio','alimentos')),EMPTY)
        self.assertEqual(suggest_category('cerveza',self.rows('ocio','ocio','alimentos','alimentos')),EMPTY)
        self.assertEqual(suggest_category('cerveza',self.rows('ocio','ocio','alimentos')),
                         {'categoria':'ocio','coincidencias':2,'total':3})

    def test_accents_and_typing_errors(self):
        for query in ['cervesa','cerbeza','serbesa']:
            self.assertEqual(suggest_category(query,self.rows('alimentos','alimentos'))['categoria'],'alimentos')
        self.assertEqual(suggest_category('CAFE',self.rows('alimentos','alimentos',description='Café'))['categoria'],'alimentos')

    def test_exact_history_takes_precedence(self):
        rows=self.rows('alimentos','alimentos') + self.rows(*(['ocio']*10),description='Cerveza y snacks')
        self.assertEqual(suggest_category('cerveza',rows)['categoria'],'alimentos')
        self.assertEqual(suggest_category('cerveza',self.rows('alimentos')+self.rows('ocio','ocio',description='Cerveza y snacks')),EMPTY)

    def test_no_unrelated_or_short_suggestions(self):
        for query in ['gas','12345','Seguro auto','    ']:
            self.assertEqual(suggest_category(query,self.rows('alimentos','alimentos')),EMPTY)

    def test_endpoint_auth_and_validation(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        path=f'/spaces/{uuid4()}/accounts/{uuid4()}/expenses/category-suggestion'
        self.assertEqual(client.get(path,params={'descripcion':'Cerveza'}).status_code,401)
        for description in ['x','x'*161,'Cerveza\n']:
            self.assertEqual(client.get(path,params={'descripcion':description}).status_code,422)
