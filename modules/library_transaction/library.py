import datetime

from sql import Null
from sql.operators import Concat
from sql.aggregate import Count, Min

from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.model import ModelSQL, ModelView, fields
from trytond.model.fields import SQL_OPERATORS
from trytond.pyson import If, Eval, Date


__all__ = [
    'User',
    'Checkout',
    'Book',
    'Exemplary',
    'Subscription',
    'SubcriptionConfiguration'
    ]


class User(ModelSQL, ModelView):
    'Library User'
    __name__ = 'library.user'
    _rec_name = 'name'

    name = fields.Char('Nom', required=True)
    cin = fields.Char('Numéro de la carte d\'identité')
    email = fields.Char('Email', required=True)
    adress = fields.Char('Adresse')
    phone = fields.Char('Numéro de téléphone', required=True)
    registration_date = fields.Date('Date d\'inscription', domain=[
            If(~Eval('registration_date'), [],
                [('registration_date', '<=', Date())])],
        help='La date à laquelle le client s\'est inscris dans la bibliothéque')
    checkouts = fields.One2Many('library.user.checkout', 'user', 'Emprunts associés')
    checkedout_books = fields.Function(
        fields.Integer('Livres rendus', help='Le nombre de livres que le client '
            'a récemment rendu'),
        'getter_checkedout_books')
    late_checkedout_books = fields.Function(
        fields.Integer('Livres retournés tard', help='Le nombre de livres '
            'que le client a rendu tard'),
        'getter_checkedout_books')
    expected_return_date = fields.Function(
        fields.Date('Date de retour prévue', help='La date que le client '
            'est (ou était) supposé rendre ses livres'),
        'getter_checkedout_books', searcher='search_expected_return_date')
    #subscription = fields.One2One(origin='library.user.subscription',target='user',string='Abonnement')
    #subscription = fields.One2One('library.user.subscription', 'user', target='library.user', relation_name='user_subscription_relation', string='Abonnement')
    #subscription = fields.One2One(origin='library.user.subscription',target= 'user', string='Abonnement')


    @classmethod
    def default_registration_date(cls):
        return datetime.date.today()
    
    @classmethod
    def getter_checkedout_books(cls, users, name):
        checkout = Pool().get('library.user.checkout').__table__()
        cursor = Transaction().connection.cursor()
        default_value = None
        if name not in ('checkedout_books', 'late_checkedout_books'):
            default_value = 0
        result = {x.id: default_value for x in users}
        column, where = cls._get_checkout_column(checkout, name)
        cursor.execute(*checkout.select(checkout.user, column,
                where=where & checkout.user.in_([x.id for x in users]),
                group_by=[checkout.user]))
        for user_id, value in cursor.fetchall():
            result[user_id] = value
            if name == 'expected_return_date' and value:
                result[user_id] += datetime.timedelta(days=20)
        return result

    @classmethod
    def _get_checkout_column(cls, checkout_table, name):
        column, where = None, None
        if name == 'checkedout_books':
            column = Count(checkout_table.id)
            where = checkout_table.return_date != None
        elif name == 'late_checkedout_books':
            column = Count(checkout_table.id)
            where = ((checkout_table.return_date != None) &
        (checkout_table.date +datetime.timedelta(days=20) <datetime.date.today() +
                datetime.timedelta(days=20)))
        elif name == 'expected_return_date':
            column = Min(checkout_table.date)
            where = checkout_table.return_date == Null
        else:
            raise Exception('Invalid function field name %s' % name)
        return column, where

    @classmethod
    def search_expected_return_date(cls, name, clause):
        user = cls.__table__()
        checkout = Pool().get('library.user.checkout').__table__()
        _, operator, value = clause
        if isinstance(value, datetime.date):
            value = value + datetime.timedelta(days=-20)
        if isinstance(value, (list, tuple)):
            value = [(x + datetime.timedelta(days=-20) if x else x)
                for x in value]
        Operator = SQL_OPERATORS[operator]

        query_table = user.join(checkout, 'LEFT OUTER',
            condition=checkout.user == user.id)

        query = query_table.select(user.id,
            where=(checkout.return_date == Null) |
            (checkout.id == Null),
            group_by=user.id,
            having=Operator(Min(checkout.date), value))
        return [('id', 'in', query)]
    
    
    @classmethod
    @ModelView.button_action('library.act_open_user_subscription')
    def create_subscription(cls, subscription):
        pass

class Checkout(ModelSQL, ModelView):
    'Checkout'
    __name__ = 'library.user.checkout'

    user = fields.Many2One('library.user', 'Client', required=True,
        ondelete='CASCADE')
    exemplary = fields.Many2One('library.book.exemplary', 'Exemplaire',
        required=True, ondelete='CASCADE')
    date = fields.Date('Date d\'emprunt', required=True, domain=[
            ('date', '<=', Date())])
    return_date = fields.Date('Date de retour effective', domain=[
            If(~Eval('return_date'), [],
                [('return_date', '<=', Date()),
                    ('return_date', '>=', Eval('date'))])],
        depends=['date'])
    expected_return_date = fields.Function(
        fields.Date('Date de retour prévue', help='La date à laquelle  '
            'l\'exemplaire est supposé être rendu'),
        'getter_expected_return_date', searcher='search_expected_return_date')

    def getter_expected_return_date(self, name):
        return self.date + datetime.timedelta(days=20)

    @classmethod
    def search_expected_return_date(cls, name, clause):
        _, operator, value = clause
        if isinstance(value, datetime.date):
            value = value + datetime.timedelta(days=-20)
        if isinstance(value, (list, tuple)):
            value = [(x + datetime.timedelta(days=-20) if x else x)
                for x in value]
        return [('date', operator, value)]


class Book(metaclass=PoolMeta):
    __name__ = 'library.book'

    is_available = fields.Function(
        fields.Boolean('Est disponible', help='Si coché, au moins un exemplaire '
            'de ce livre est actuellement disponible pour l\'emprunt'),
        'getter_is_available', searcher='search_is_available')

    @classmethod
    def getter_is_available(cls, books, name):
        pool = Pool()
        checkout = pool.get('library.user.checkout').__table__()
        exemplary = pool.get('library.book.exemplary').__table__()
        book = cls.__table__()
        result = {x.id: False for x in books}
        cursor = Transaction().connection.cursor()
        cursor.execute(*book.join(exemplary,
                condition=(exemplary.book == book.id)
                ).join(checkout, 'LEFT OUTER',
                condition=(exemplary.id == checkout.exemplary)
                ).select(book.id,
                where=(checkout.return_date != Null) | (checkout.id == Null)))
        for book_id, in cursor.fetchall():
            result[book_id] = True
        return result

    @classmethod
    def search_is_available(cls, name, clause):
        _, operator, value = clause
        if operator == '!=':
            value = not value
        pool = Pool()
        checkout = pool.get('library.user.checkout').__table__()
        exemplary = pool.get('library.book.exemplary').__table__()
        book = cls.__table__()
        query = book.join(exemplary,
            condition=(exemplary.book == book.id)
            ).join(checkout, 'LEFT OUTER',
            condition=(exemplary.id == checkout.exemplary)
            ).select(book.id,
            where=(checkout.return_date != Null) | (checkout.id == Null))
        return [('id', 'in' if value else 'not in', query)]
    


class Exemplary(metaclass=PoolMeta):
    __name__ = 'library.book.exemplary'

    checkouts = fields.One2Many('library.user.checkout', 'exemplary',
        'Emprunts')
    is_available = fields.Function(
        fields.Boolean('Est disponible', help='Si coché, l\' exemplaire est '
            'actuellement disponible pour l\'emprunt'),
        'getter_is_available', searcher='search_is_available')

    @classmethod
    def getter_is_available(cls, exemplaries, name):
        checkout = Pool().get('library.user.checkout').__table__()
        cursor = Transaction().connection.cursor()
        result = {x.id: True for x in exemplaries}
        cursor.execute(*checkout.select(checkout.exemplary,
                where=(checkout.return_date == Null)
                & checkout.exemplary.in_([x.id for x in exemplaries])))
        for exemplary_id, in cursor.fetchall():
            result[exemplary_id] = False
        return result

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('identifier',) + tuple(clause[1:]),
            ('book.title',) + tuple(clause[1:]),
            ]

    @classmethod
    def order_rec_name(cls, tables):
        exemplary, _ = tables[None]
        book = tables.get('book')

        if book is None:
            book = Pool().get('library.book').__table__()
            tables['book'] = {None: (book, book.id == exemplary.book)}

        return [Concat(book.title, exemplary.identifier)]

    @classmethod
    def search_is_available(cls, name, clause):
        _, operator, value = clause
        if operator == '!=':
            value = not value
        pool = Pool()
        checkout = pool.get('library.user.checkout').__table__()
        exemplary = cls.__table__()
        query = exemplary.join(checkout, 'LEFT OUTER',
            condition=(exemplary.id == checkout.exemplary)
            ).select(exemplary.id,
            where=(checkout.return_date != Null) | (checkout.id == Null))
        return [('id', 'in' if value else 'not in', query)]


class Subscription(ModelView,ModelSQL):
      'User Subscription'
      __name__ = 'library.user.subscription'

      start_date = fields.Date('Date de début', required=True)
      expiration_date = fields.Function(fields.Date('Date d\'expiration'),'on_change_with_expiration_date')
      subscription_type = fields.Selection([('annuel', 'Annuel'), ('mensuel', 'Mensuel'),('trimestriel','Trimestriel'),['semestriel','Semestriel']] , 'Type d\'abonnement',required=True)
      status = fields.Function(fields.Boolean('Est encore valable'),'getter_status')
      config = fields.Many2One('library.user.subscription.config', 'Paramètrage Abonnement',
        ondelete='CASCADE')
      subscription_fee = fields.Function(fields.Numeric('Frais total', digits=(16,2)),'getter_subscription_fee')
      #user = fields.One2One(origin='library.user', target='subscription', string='Client')
     #class trytond.model.fields.One2One(, , , string[, datetime_field[, \**options]])¶
      #user = fields.One2One('library.user', 'subscription', target='library.user.subscription', string='CLient')
      @classmethod
      def default_start_date(cls):
       return datetime.date.today()

     
      @classmethod
      def getter_subscription_fee(cls, subscriptions, name):
        result = {x.id: None for x in subscriptions}
        Config   = Pool().get('library.user.subscription.config')
        config = Config.search([], limit=1)
        first_config = config[0]
        unit_subscription_fee = first_config.unit_subscription_fee
        discount_annual_subscription_fee = first_config.discount_annual_subscription_fee
        discount_trimestrial_subscription_fee = first_config.discount_trimestrial_subscription_fee
        discount_semestrial_subscription_fee = first_config.discount_semestrial_subscription_fee
        for subscription in subscriptions:
         
         subscription_type = subscription.subscription_type

         if subscription_type == 'annuel':
            result[subscription.id] = unit_subscription_fee * 12 * (1 - (discount_annual_subscription_fee / 100))
         elif subscription_type == 'mensuel':
            result[subscription.id] = unit_subscription_fee
         elif subscription_type == 'trimestriel':
            result[subscription.id] = unit_subscription_fee * 3 * (1 - (discount_trimestrial_subscription_fee / 100))
         else:
            result[subscription.id] = unit_subscription_fee * 6 * (1 - (discount_semestrial_subscription_fee / 100))
    
         return result
      
      def getter_status(self, name):
          if self.expiration_date < datetime.date.today():
              return False
          return True
      
      @fields.depends('subscription_type', 'start_date')
      def on_change_with_expiration_date(self, name=None):
       if self.subscription_type and self.start_date:
         if self.subscription_type == 'annuel':
            duration = datetime.timedelta(days=365)
         elif self.subscription_type == 'mensuel':
            duration = datetime.timedelta(days=30)
         elif self.subscription_type == 'trimestriel':
            duration = datetime.timedelta(days=90)
         elif self.subscription_type == 'semestriel':
            duration = datetime.timedelta(days=180)
         else:
            return  

         expiration_date = self.start_date + duration
         return expiration_date
     
            
              
class SubcriptionConfiguration(ModelSQL, ModelView):
    'User Subscription Configuration '
    __name__ = 'library.user.subscription.config'

    unit_subscription_fee = fields.Numeric('Prix d\'abonnement mensuel', digits=(16,2), required=True)
    discount_trimestrial_subscription_fee = fields.Numeric('Remise pour le prix trimestriel', digits=(16,2), required=True)
    discount_semestrial_subscription_fee = fields.Numeric('Remise pour le prix semestriel', digits=(16,2), required=True)
    discount_annual_subscription_fee = fields.Numeric('Remise pour le prix annuel', digits=(16,2), required=True)
    subscriptions = fields.One2Many('library.user.subscription','config','Abonnements')

    




              
                 
 






    

    