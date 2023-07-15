import datetime

from trytond.pool import Pool
from trytond.model import ModelView, fields
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, StateAction
from trytond.wizard import Button
from trytond.pyson import Date, Eval, PYSONEncoder
from trytond.exceptions import UserError


__all__ = [
    'Borrow',
    'BorrowSelectBooks',
    'Return',
    'ReturnSelectCheckouts',
    ]


class Borrow(Wizard):
    'Borrow books'
    __name__ = 'library.user.borrow'

    start_state = 'select_books'
    select_books = StateView('library.user.borrow.select_books',
        'library_transaction.borrow_select_books_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Emprunter', 'borrow', 'tryton-go-next', default=True)])
    borrow = StateTransition()
    checkouts = StateAction('library_transaction.act_open_user_checkout')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        """
        cls._error_messages.update({
                'unavailable': 'Exemplary %(exemplary)s is unavailable for '
                'checkout',
                })
        """        

    def default_select_books(self, name):
        user = None
        exemplaries = []
        if Transaction().context.get('active_model') == 'library.user':
            user = Transaction().context.get('active_id')
        elif Transaction().context.get('active_model') == 'library.book':
            books = Pool().get('library.book').browse(
                Transaction().context.get('active_ids'))
            for book in books:
                if not book.is_available:
                    continue
                for exemplary in book.exemplaries:
                    if exemplary.is_available:
                        exemplaries.append(exemplary.id)
                        break
        return {
            'user': user,
            'exemplaries': exemplaries,
            'date': datetime.date.today(),
            }

    def transition_borrow(self):
        Checkout = Pool().get('library.user.checkout')
        exemplaries = self.select_books.exemplaries
        user = self.select_books.user
        checkouts = []
        for exemplary in exemplaries:
            if not exemplary.is_available:
                raise UserError('L\'exemplaire n\'est pas disponible pour l\'emprunt', {
                        'exemplaire': exemplary.rec_name})
            checkouts.append(Checkout(
                    user=user, date=self.select_books.date,
                    exemplary=exemplary))
        Checkout.save(checkouts)
        self.select_books.checkouts = checkouts
        return 'checkouts'

    def do_checkouts(self, action):
        action['pyson_domain'] = PYSONEncoder().encode([
                ('id', 'in', [x.id for x in self.select_books.checkouts])])
        return action, {}


class BorrowSelectBooks(ModelView):
    'Select Books'
    __name__ = 'library.user.borrow.select_books'

    user = fields.Many2One('library.user', 'Client', required=True)
    exemplaries = fields.Many2Many('library.book.exemplary', None, None,
        'Exemplaires', required=True, domain=[('is_available', '=', True)])
    date = fields.Date('Date', required=True, domain=[('date', '<=', Date())])
    checkouts = fields.Many2Many('library.user.checkout', None, None,
        'Emprunts', readonly=True)


class Return(Wizard):
    'Return'
    __name__ = 'library.user.return'

    start_state = 'select_checkouts'
    select_checkouts = StateView('library.user.return.checkouts',
        'library_transaction.return_checkouts_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Retourner', 'return_', 'tryton-go-next', default=True)])
    return_ = StateTransition()

    @classmethod
    def __setup__(cls):
        super().__setup__()
        """
        cls._error_messages.update({
                'multiple_users': 'You cannot return checkouts from different '
                'users at once',
                'available': 'Cannot return an available exemplary',
                })
        """
    def default_select_checkouts(self, name):
        Checkout = Pool().get('library.user.checkout')
        user = None
        checkouts = []
        if Transaction().context.get('active_model') == 'library.user':
            user = Transaction().context.get('active_id')
            checkouts = [x for x in Checkout.search([
                        ('user', '=', user), ('return_date', '!=', None)])]
        elif (Transaction().context.get('active_model') ==
                'library.user.checkout'):
            checkouts = Checkout.browse(
                Transaction().context.get('active_ids'))
            if len({x.user for x in checkouts}) != 1:
                raise UserError('On ne peut pas retourner des livres de plusieurs clients en même temps  ')
            if any(x.is_available for x in checkouts):
                raise UserError('On ne peut pas retourner un libre disponible')
            user = checkouts[0].user.id
        return {
            'user': user,
            'checkouts': [x.id for x in checkouts],
            'date': datetime.date.today(),
            }

    def transition_return_(self):
        Checkout = Pool().get('library.user.checkout')
        Checkout.write(list(self.select_checkouts.checkouts), {
                'return_date': self.select_checkouts.date})
        return 'end'


class ReturnSelectCheckouts(ModelView):
    'Select Checkouts'
    __name__ = 'library.user.return.checkouts'

    user = fields.Many2One('library.user', 'User', required=True)
    checkouts = fields.Many2Many('library.user.checkout', None, None,
        'Checkouts', domain=[('user', '=', Eval('user')),
            ('return_date', '=', None)])
    date = fields.Date('Date', required=True, domain=[('date', '<=', Date())])


class CreateSubscription(Wizard):
    'Create Subscription'
    __name__ = 'library.book.create_exemplaries'

    start_state = 'parameters'
    parameters = StateView('library.book.create_subscription.parameters',
        'library_transaction.create_subscription_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Créer', 'create_subscription', 'tryton-go-next',
                default=True)])
    create_subscription = StateTransition()
    open_subscriptions = StateAction('library_transaction.act_open_user_subscription')

    @classmethod
    def __setup__(cls):
        super().__setup__()
       
    def default_parameters(self, name):
        if Transaction().context.get('active_model', '') != 'library.user':
            raise UserError('Cette action doit être déclenché du model client')
        return {
            'start_date': datetime.date.today(),
            'user': Transaction().context.get('active_id'),
            'subscription_type':'mensuel'
            }

    def transition_create_subscription(self):
      
        Subscription = Pool().get('library.user.subscription')
        subscription = Subscription()
        subscription.user = self.parameters.user
        subscription.start_date = self.parameters.start_date
        subscription.subscription_type = self.parameters.subscription_type
       
        Subscription.save(subscription)

        return 'open_subscription'

    def do_open_subscription(self, action):
    

     subscription_id = self.create_subscription()
   

     return {
        'name': 'Créer Abonnement',
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'library.user.subscription',
        'res_id': subscription_id,
        'views': [(False, 'form')],
        'type': 'ir.actions.act_window',
        'target': 'current',
        'context': {
            'form_view_ref': 'library_transaction.act_open_user_subscription_view_form',
        },
    }

    

class CreateSubscriptionParameters(ModelView):
      'Create Subscription Parameters'
      __name__ = 'library.user.create_subscription.parameters'

      user = fields.Many2One('library.user', 'Client', readonly=True)
      subscription_type = fields.Selection([('annuel', 'Annuel'), ('mensuel', 'Mensuel'),('trimestriel','Trimestriel'),('semestriel','Semestriel')], 'Type d\'abonnement',
        required=True
        )
      start_date = fields.Date('Date de début de l\'abonnement ', required=True)
    
       
