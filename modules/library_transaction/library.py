import datetime

from sql import Null
from sql.operators import Concat
from sql.aggregate import Count, Min
import random

from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError

from trytond.model import ModelSQL, ModelView, fields
from trytond.model.fields import SQL_OPERATORS
from trytond.pyson import If, Eval, Date
from trytond.config import config
from email.mime.text import MIMEText
import smtplib
from decimal import Decimal
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

import web_pdb


__all__ = [
    'User',
    'Checkout',
    'Book',
    'Exemplary',
    'Subscription',
    'SubcriptionConfiguration'
    'UserSubscriptionRelation',
    'Invoice',
    'InvoiceLine'

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
    invoices = fields.One2Many('library.user.invoice','user','Factures')

    
   
    subscription = fields.One2One('library.user_subscription_relation','user','subscription','Abonnement')
    #has_subscription = fields.Function(fields.Boolean('A un abonnement'),'getter_has_subscription')
 

    @classmethod
    def __setup__(cls):
     super().__setup__()
     cls._buttons.update({
        'create_subscription': {
            'invisible': bool(Eval('subscription')),
        },
        'renew_subscription': {
            'invisible': ~bool(Eval('subscription'))
        },
    })

    # def getter_has_subscription(self, name):
    #  return self.subscription != None

    @classmethod
    def send_late_return_emails(cls):
        users = cls.search([
            ('expected_return_date', '<', datetime.date.today()),
        ])
        for user in users:
        
            subject = 'Rappel : Retour de livres en retard'
            message = f"Cher {user.name},\n\nCe message est pour vous rappeler de retourner les livres empruntés à la bibliothèque.\nVeuillez les retourner dès que possible pour éviter des frais de retard.\n\nCordialement,\nBibliothèque"

            # Créer l'objet e-mail
            email = MIMEText(message)
            email['Subject'] = subject
            email['From'] = 'eya.raouine@insat.ucar.tn'
            email['To'] = user.email

            # Envoyer l'e-mail via le serveur SMTP
            smtp_server = config.get('smtp_server','smtp.gmail.com')
            smtp_port = config.get('smtp_port', 587)
            smtp_username = config.get('smtp_username', 'eya.raouine@insat.ucar.tn')
            smtp_password = config.get('smtp_password', 'olfahatem15')

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(email)
     
  
        

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
        (checkout_table.return_date > checkout_table.date +
                datetime.timedelta(days=20)))
        elif name == 'expected_return_date':
            column = Min(checkout_table.date)
            where = checkout_table.return_date == Null
        else:
            raise Exception('Champs fonction invalide %s' % name)
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
    @ModelView.button_action('library_transaction.act_create_user_subscription')
    def create_subscription(cls, subscription):
        pass
    
    @classmethod
    @ModelView.button_action('library_transaction.act_open_user_subscription')
    def renew_subscription(cls, subscription):
        pass
    
            

    """
    @classmethod  
    @ModelView.button
    def renew_subscription(cls, users):
   
        action = {
        'name': 'Renouveller Aboonement',
        'type': 'ir.action.act_window.view"',
        'res_model': 'library.user',
        'view_mode': 'form',
        'view_type': 'form',
        'res_id': cls.subscription.id if cls.subscription else None,
        'view_id': 'act_open_user_subscription_view_form',
        'target': 'new',
        }
        return action 
    """    
    

    """
    @ModelView.button_action('library_transaction.act_open_user_subscription_view_form')
    def renew_subscription(self, records):
      Subscription = Pool().get('library.user.subscription')

      action = {
        'name': 'Renouveler Abonnement',
        'type': 'ir.action.act_window',
        'res_model': 'library.user',
        'view_mode': 'form',
        'view_type': 'form',
        'target': 'new',
    }

      user_id = Transaction().context.get('active_id')

    # Get the specific user's subscription record
      subscription = Subscription.search([('user', '=', user_id)], limit=1)

      if subscription:
        action['res_id'] = subscription.id

      return action
    """
    """
    @classmethod   
    @ModelView.button
    def renew_subscription(cls, users):
     pool = Pool()

     Subscription = pool.get('library.user.subscription')

     action = {
        'name': 'Renouveler abonnement',
        'id': 'library_transaction.act_open_user_subscription',
        'context': {
            'form_view_ref': 'library_transaction.act_open_user_subscription_view_form',
        },
        'type':'ir.actions.act_window',
        'res_model': 'library.user.subscription',
        'view_mode': 'form',
        'view_type': 'form',
        'target': 'new',

    }

     for user in users:
        # Replace 'YOUR_USER_ID_FIELD_NAME' with the actual field name that stores the user ID
        if Transaction().context.get('active_id') == user.id :

          # Get the specific user's subscription record
          subscriptions = Subscription.search([('user', '=', user.id)])
          if subscriptions:
            # Select the first subscription record
            subscription = subscriptions[0]
            action['res_id'] = subscription.id
          else:
            action['res_id'] = None


        
     return action
    """ 
    
"""
    @ModelView.button
    def renew_subscription(self, action):
      if action and isinstance(action, list) and len(action) > 0:
        action = action[0]
        action.setdefault('name', 'Créer Abonnement')
        action.setdefault('view_type', 'form')
        action.setdefault('view_mode', 'form')
        action.setdefault('res_model', 'library.user.subscription')
        action.setdefault('res_id', self.subscription.id)
        action.setdefault('views', [(False, 'form')])
        action.setdefault('type', 'ir.actions.act_window')
        action.setdefault('target', 'current')
        action.setdefault('context', {
            'form_view_ref': 'library_transaction.act_open_user_subscription_view_form',
        })

      return action, {}
"""      

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

    is_available_for_borrow  = fields.Function(
        fields.Boolean('Disponible pour l\'emprunt', help='Si coché, au moins un exemplaire '
            'de ce livre est actuellement disponible pour l\'emprunt'),
        'getter_is_available_for_borrow', searcher='search_is_available_for_borrow')

    number_of_exemplaries_for_sale = fields.Function(fields.Integer('Nombre d\'exemplaires pour la vente'),
                                                     'getter_number_of_exemplaries_for_sale')
    number_of_exemplaries_for_borrow = fields.Function(fields.Integer('Nombre d \'exemplaires pour l\'emprunt'),
                                                            'getter_number_of_exemplaries_for_borrow')
    sale_price = fields.Numeric('Prix de vente HT')
    discount = fields.Numeric('Remise', digits=(16,2))
    invoice_lines = fields.One2Many('library.user.invoice.line','book','Lignes Factures')
    
    @classmethod
    def getter_number_of_exemplaries_for_sale(self,books, name):
       # return self.number_of_exemplaries - self.number_of_exemplaries_for_borrow
        result = {x.id: 0 for x in books}
        Exemplary = Pool().get('library.book.exemplary')
        exemplary = Exemplary.__table__()

        cursor = Transaction().connection.cursor()
        cursor.execute(*exemplary.select(exemplary.book, Count(exemplary.id),
    where=((exemplary.book.in_([x.id for x in books])) &
           (exemplary.is_for_sale == True)),
    group_by=[exemplary.book]))

        for book_id, count in cursor.fetchall():
            result[book_id] = count
        return result
        

    
    @classmethod
    def getter_number_of_exemplaries_for_borrow(cls,books, name):

        result = {x.id: 0 for x in books}
        Exemplary = Pool().get('library.book.exemplary')
        exemplary = Exemplary.__table__()

        cursor = Transaction().connection.cursor()
        cursor.execute(*exemplary.select(exemplary.book, Count(exemplary.id),
    where=((exemplary.book.in_([x.id for x in books])) &
           (exemplary.is_for_sale == False)),
    group_by=[exemplary.book]))

        for book_id, count in cursor.fetchall():
            result[book_id] = count
        return result
    @classmethod   
    def default_discount(cls):
        return Decimal(0.0)
    
    
    @classmethod
    def getter_is_available_for_borrow(cls, books, name):
        
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
                where=(checkout.return_date != Null) | (checkout.id == Null) & (exemplary.is_for_sale == False)))
        for book_id, in cursor.fetchall():
            result[book_id] = True
        return result

   
    
    @classmethod
    def search_is_available_for_borrow(cls, name, clause):
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
            where=(checkout.return_date != Null) | (checkout.id == Null) & (exemplary.is_for_sale == False))
        return [('id', 'in' if value else 'not in', query)]
    


class Exemplary(metaclass=PoolMeta):
    __name__ = 'library.book.exemplary'

    checkouts = fields.One2Many('library.user.checkout', 'exemplary',
        'Emprunts')
    is_available_for_borrow = fields.Function(
        fields.Boolean('Disponible pour l\'emprunt', help='Si coché, l\' exemplaire est '
            'actuellement disponible pour l\'emprunt'),
        'getter_is_available_for_borrow', searcher='search_is_available_for_borrow')
    is_for_sale = fields.Boolean('Pour la vente')
   
    



    """
    @classmethod
    def getter_is_available_for_borrow(cls, exemplaries, name):
        checkout = Pool().get('library.user.checkout').__table__()
        cursor = Transaction().connection.cursor()
        exemplary = cls.__table__()
        result = {x.id: True for x in exemplaries}
        cursor.execute(*checkout.select(checkout.exemplary,
                where=(checkout.return_date == Null)
                & checkout.exemplary.in_([x.id for x in exemplaries])
                   & (exemplary.is_for_sale == False)))
        for exemplary_id, in cursor.fetchall():
            result[exemplary_id] = False
        return result
    """
    @classmethod
    def getter_is_available_for_borrow(cls, exemplaries, name):
     checkout = Pool().get('library.user.checkout').__table__()
     cursor = Transaction().connection.cursor()
     exemplary = cls.__table__()

     cursor.execute(*exemplary.join(checkout, 'LEFT OUTER',
        condition=(exemplary.id == checkout.exemplary)
    ).select(exemplary.id,
        where=(exemplary.id.in_([x.id for x in exemplaries])
               & (exemplary.is_for_sale == False)
               & ((checkout.return_date != Null) | (checkout.id == Null)))))

     available_exemplaries = [exemplary_id for exemplary_id, in cursor.fetchall()]

     result = {x.id: x.id  in available_exemplaries for x in exemplaries}
    
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
    def search_is_available_for_borrow(cls, name, clause):
     _, operator, value = clause
     if operator == '!=':
        value = not value
     pool = Pool()
     checkout = pool.get('library.user.checkout').__table__()
     exemplary = cls.__table__()
     query = exemplary.join(checkout, 'LEFT OUTER',
        condition=(exemplary.id == checkout.exemplary)
    ).select(exemplary.id,
        where=((checkout.return_date != Null) | (checkout.id == Null))
              & (exemplary.is_for_sale == False))

     if not value:
      
        query = ~query

     return [('id', 'in' if value else 'not in', query)]
 

class Subscription(ModelView,ModelSQL):
      'User Subscription'
      __name__ = 'library.user.subscription'

      start_date = fields.Date('Date de début', required=True)
      expiration_date = fields.Function(fields.Date('Date d\'expiration'),'on_change_with_expiration_date')
      subscription_type = fields.Selection([
          ('annuel', 'Annuel'),
          ('mensuel', 'Mensuel'),
          ('trimestriel','Trimestriel'),
          ('semestriel','Semestriel')
          ],
         'Type d\'abonnement',
          required=True
        )
      status = fields.Function(fields.Boolean('Encore valable'),'getter_status')
      config = fields.Many2One('library.user.subscription.config', 'Paramètrage Abonnement',
        ondelete='CASCADE')
      subscription_fee = fields.Function(fields.Numeric('Frais total', digits=(16,2)),'getter_subscription_fee')
      user = fields.One2One('library.user_subscription_relation', 'subscription','user',  'Client')

      @classmethod
      def default_start_date(cls):
       return datetime.date.today()

  
      def getter_subscription_fee(self, name):
        config = Pool().get('library.user.subscription.config').search([])[0]
        subscription_fee = Decimal(0)
        subscription_type = self.subscription_type
        unit_subscription_fee = config.unit_subscription_fee
        discount_annual_subscription_fee = config.discount_annual_subscription_fee
        discount_trimestrial_subscription_fee = config.discount_trimestrial_subscription_fee
        discount_semestrial_subscription_fee = config.discount_semestrial_subscription_fee
        if subscription_type == 'annuel':
            subscription_fee = unit_subscription_fee * 12 * (1 - (discount_annual_subscription_fee / 100))
        elif subscription_type == 'mensuel':
            subscription_fee  = unit_subscription_fee
        elif subscription_type == 'trimestriel':
            subscription_fee  = unit_subscription_fee * 3 * (1 - (discount_trimestrial_subscription_fee / 100))
        else:
            subscription_fee  = unit_subscription_fee * 6 * (1 - (discount_semestrial_subscription_fee / 100))
    
        return subscription_fee 

          
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

class UserSubscriptionRelation(ModelSQL, ModelView): 
    'Library User Subscription Relation'
    __name__ = 'library.user_subscription_relation'
    
    user = fields.Many2One('library.user', 'Client')
    subscription = fields.Many2One('library.user.subscription','Abonnement')




        
class Invoice(ModelSQL, ModelView):
     'Library Account Invoice'
     __name__ = 'library.user.invoice'
    
     user = fields.Many2One('library.user','Client')
     invoice_lines = fields.One2Many('library.user.invoice.line','invoice',
                                     'Lignes associées')
     invoice_date = fields.Date('Date de facturation')
     total_sale_price_HT = fields.Function(fields.Numeric('Total HT',digits=(16,2)),
                                         'getter_total_sale_price_HT')
     total_HT_after_discount = fields.Function(fields.Numeric('Total HT aprés remise', digits=(16,2)),
                 'getter_total_HT_after_discount')    
     total_sale_price_TTC = fields.Function(fields.Numeric('Total TTC', digits=(16,2)),
                                           'getter_total_sale_price_TTC')
     @classmethod
     def __setup__(cls):
      super().__setup__()
      cls._buttons.update({
        'generate_invoice_pdf': {
            
        },
    
    })
  
     
     def getter_total_sale_price_HT(self,name):
        total = 0
        for line in self.invoice_lines:
            total +=line.sale_price_HT
        return total   
     
     def getter_total_HT_after_discount(self,name):
        total = 0
        for line in self.invoice_lines:
            total +=line.sale_price_HT_after_discount
        return total   
     
     def getter_total_sale_price_TTC(self,name):
         total = 0
         for line in self.invoice_lines:
             total +=line.sale_price_TTC
         return total   
      
    #  def generate_invoice_pdf(self, filename):
    #     """
    #     Generate a PDF invoice for the current invoice object and save it to the specified filename.
    #     """
    #     # Create a new canvas with the specified filename and page size
        
    #     c = canvas.Canvas(filename, pagesize=letter)

    #     # Write the invoice details to the PDF
    #     c.setFont("Helvetica", 12)
    #     c.drawString(1 * inch, 10 * inch, "Numéro de la facture: {}".format(self.id))
    #     c.drawString(1 * inch, 9.5 * inch, "Date de la facture: {}".format(self.invoice_date))
    #     c.drawString(1 * inch, 9 * inch, "Client: {}".format(self.user.name))

    #     # Calculate and write invoice line details
    #     line_height = 8.5 * inch
    #     for line in self.invoice_lines:
    #         line_height -= 0.3 * inch
    #         c.drawString(1 * inch, line_height, "Book: {}".format(line.book.name))
    #         c.drawString(2 * inch, line_height - 0.2 * inch, "Quantité: {}".format(line.number_of_exemplaries_to_sell))
    #         c.drawString(3 * inch, line_height - 0.4 * inch, "Prix (HT): {}".format(line.sale_price_HT))
    #         c.drawString(4 * inch, line_height - 0.6 * inch, "Prix (HT aprés remise): {}".format(line.sale_price_HT_after_discount))
    #         c.drawString(5 * inch, line_height - 0.8 * inch, "Prix (TTC): {}".format(line.sale_price_TTC))

    #     # Draw a line at the bottom of the page
    #     c.line(1 * inch, 1 * inch, 7.5 * inch, 1 * inch)

    #     # Save the PDF
    #     c.save()

    #  def generate_invoice_pdf_action(self):
    #     """
    #     Action method called when the "Generate Invoice PDF" button is clicked.
    #     """
    #     # Generate the PDF and save it with a specific filename (e.g., invoice_1.pdf)
    #     filename = 'facture_{}.pdf'.format(self.id)
    #     self.generate_invoice_pdf(filename)

    #     return {
    #         'warning': {
    #             'title': 'PDF Généré',
    #             'message': 'La Facture PDF a été générée avec succés.',
    #         },
    #     }    
     @classmethod
     @ModelView.button_action('library_transaction.act_generate_invoice_pdf')
     def generate_invoice_pdf(cls, invoice):
           pass
    

class InvoiceLine(ModelSQL, ModelView):
     'Library Account Invoice Line'
     __name__ = 'library.user.invoice.line' 

     book = fields.Many2One('library.book','Livre')
     number_of_exemplaries_to_sell = fields.Integer('Nombre d\'exemplaires à vendre', required=True)
     taxe = fields.Numeric('Taxe')   
     invoice = fields.Many2One('library.user.invoice','Facture Associée') 
     sale_price_HT = fields.Function(fields.Numeric('Prix HT'),'getter_sale_price_HT')
     sale_price_HT_after_discount = fields.Function(fields.Numeric('Prix HT aprés remise'),'getter_sale_price_HT_after_discount')
     sale_price_TTC = fields.Function(fields.Numeric('Prix TTC'),'getter_sale_price_TTC')

     @classmethod
     def default_taxe(cls):
         return Decimal(6.0)
    
     @classmethod
     def create(cls, vlist):
         # Surcharge de la méthode create pour tester la quantité et diminuer le stock
       
        pool = Pool()
        Book = pool.get('library.book')
        Exemplary = pool.get('library.book.exemplary')

        for values in vlist:
           book_id = values.get('book')
           number_of_exemplaries_to_sell = values.get('number_of_exemplaries_to_sell')

           if not book_id:
                continue

           books = Book.search([('id', '=', book_id)])
           if books:
                book =books[0]

                if number_of_exemplaries_to_sell > book.number_of_exemplaries_for_sale:
                  raise UserError('Quantité d\'exemplaires en stock insuffisante.')

                exemplaries_to_remove = Exemplary.search([
                    ('book', '=', book.id),
                    ('is_for_sale', '=', 'True'),
                ], limit=number_of_exemplaries_to_sell)
                Exemplary.delete(exemplaries_to_remove)

                # Mettre à jour le nombre d'exemplaires restant dans le modèle library.book
              
                # book.number_of_exemplaries_for_sale -= number_of_exemplaries_to_sell
                # book.save()
              

        return super(InvoiceLine, cls).create(vlist) 

    
     def getter_sale_price_HT(self,name):
         
       
        return self.book.sale_price * self.number_of_exemplaries_to_sell
    
     def getter_sale_price_HT_after_discount(self,name):
       if self.book.discount == 0.0:
           return self.book.sale_price * self.number_of_exemplaries_to_sell
       return self.book.sale_price * self.number_of_exemplaries_to_sell*(1-(self.book.discount/100))
     
     def getter_sale_price_TTC(self, name):
        if self.book.discount == 0.0:
               return self.book.sale_price * self.number_of_exemplaries_to_sell+ self.book.sale_price * self.number_of_exemplaries_to_sell*(self.taxe/100)
        return self.book.sale_price * self.number_of_exemplaries_to_sell*(1-(self.book.discount/100))+ self.book.sale_price * self.number_of_exemplaries_to_sell*(1-(self.book.discount/100))*(self.taxe/100) 
    
    



        








              
                 
 






    

    