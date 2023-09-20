from trytond.pool import Pool

from . import library
from . import wizard


def register():
    Pool.register(
        library.User,
        library.Checkout,
        library.Book,
        library.Exemplary,
        library.Subscription,
        library.SubcriptionConfiguration,
        library.UserSubscriptionRelation,
        library.Invoice,
        library.InvoiceLine,
        wizard.BorrowSelectBooks,
        wizard.ReturnSelectCheckouts,
        wizard.CreateSubscriptionParameters,
        module='library_transaction', type_='model')

    Pool.register(
        wizard.Borrow,
        wizard.Return,
        wizard.CreateSubscription,
        wizard.RenewSubscription,
        wizard.GenerateInvoice,
        module='library_transaction', type_='wizard')
    
        
   