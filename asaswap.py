from pyteal import *


def state(ratio_decimal_points):
    # Exchange rate decimal points
    ratio_decimal_points = Int(ratio_decimal_points)

    is_creator = Txn.sender() == App.globalGet(Bytes('CREATOR'))

    tx_ratio = Gtxn[1].asset_amount() * ratio_decimal_points / Gtxn[2].amount()

    liquidity_calc = Gtxn[2].amount() * App.globalGet(
        Bytes('TOTAL_LIQUIDITY_TOKENS')
    ) / App.globalGet(Bytes('ALGOS_BALANCE'))

    algos_calc = App.globalGet(Bytes('ALGOS_BALANCE')) * (
        App.localGet(Int(0), Bytes('USER_LIQUIDITY_TOKENS')
    ) / App.globalGet(Bytes('TOTAL_LIQUIDITY_TOKENS')))

    token_calc = App.globalGet(Bytes('TOKENS_BALANCE')) * (
        App.localGet(Int(0), Bytes('USER_LIQUIDITY_TOKENS')
    ) / App.globalGet(Bytes('TOTAL_LIQUIDITY_TOKENS')))

    on_create = Seq([
        App.globalPut(Bytes('TOKENS_BALANCE'), Int(0)),
        App.globalPut(Bytes('ALGOS_BALANCE'), Int(0)),
        App.globalPut(Bytes('TOTAL_LIQUIDITY_TOKENS'), Int(0)),
        App.globalPut(Bytes('CREATOR'), Txn.sender()),
        Return(Int(1))
    ])

    on_update = Seq([
        # Update escrow address after creating it
        Assert(And(
            is_creator,
            Txn.application_args.length() == Int(1),
        )),
        App.globalPut(Bytes('ESCROW'), Txn.application_args[0]),
        Return(Int(1))
    ])

    on_register = Seq([
        # Set default values for user
        App.localPut(Int(0), Bytes('TOKENS_TO_WITHDRAW'), Int(0)),
        App.localPut(Int(0), Bytes('ALGOS_TO_WITHDRAW'), Int(0)),
        App.localPut(Int(0), Bytes('USER_LIQUIDITY_TOKENS'), Int(0)),
        Return(Int(1))
    ])

    on_add_liquidity = Seq([
        Assert(And(
            Global.group_size() == Int(3),
            Gtxn[0].type_enum() == TxnType.ApplicationCall,
            Gtxn[1].type_enum() == TxnType.AssetTransfer,
            Gtxn[2].type_enum() == TxnType.Payment,
            Gtxn[1].asset_receiver() == App.globalGet(Bytes('ESCROW')),
            Gtxn[2].receiver() == App.globalGet(Bytes('ESCROW')),
        )),
        If(
            # Check if transactions exchange rate matches or is max 1% different from current
            App.globalGet(Bytes('EXCHANGE_RATE')) > tx_ratio,
            Assert(
                App.globalGet(Bytes('EXCHANGE_RATE')) - tx_ratio
                * ratio_decimal_points / App.globalGet(Bytes('EXCHANGE_RATE'))
                < Int(10000)
            ),
            Assert(
                tx_ratio - App.globalGet(Bytes('EXCHANGE_RATE'))
                * ratio_decimal_points / App.globalGet(Bytes('EXCHANGE_RATE'))
                < Int(10000)
            )
        ),
        If(
            # If its first transaction then add tokens directly from txn amount, else based on calculations
            App.globalGet(Bytes('TOTAL_LIQUIDITY_TOKENS')) == Int(0),
            Seq([
                App.localPut(Int(0), Bytes('USER_LIQUIDITY_TOKENS'), Gtxn[2].amount()),
                App.globalPut(Bytes('TOTAL_LIQUIDITY_TOKENS'), Gtxn[2].amount()),
            ]),
            Seq([
                App.localPut(
                    Int(0),
                    Bytes('USER_LIQUIDITY_TOKENS'),
                    App.localGet(Int(0), Bytes('USER_LIQUIDITY_TOKENS')) + liquidity_calc
                ),
                App.globalPut(
                    Bytes('TOTAL_LIQUIDITY_TOKENS'),
                    App.globalGet(Bytes('TOTAL_LIQUIDITY_TOKENS')) + liquidity_calc
                )
            ])
        ),
        App.globalPut(
            Bytes('TOKENS_BALANCE'),
            App.globalGet(Bytes('TOKENS_BALANCE')) + Gtxn[1].asset_amount()
        ),
        App.globalPut(
            Bytes('ALGOS_BALANCE'),
            App.globalGet(Bytes('ALGOS_BALANCE')) + Gtxn[2].amount()
        ),
        App.globalPut(
            Bytes('EXCHANGE_RATE'),
            App.globalGet(Bytes('ALGOS_BALANCE')) * ratio_decimal_points / App.globalGet(Bytes('TOKENS_BALANCE'))
        ),
        Return(Int(1))
    ])

    on_remove_liquidity = Seq([
        Assert(And(
            Global.group_size() == Int(1),
            Txn.application_args.length() == Int(2),
            App.localGet(Int(0), Bytes('USER_LIQUIDITY_TOKENS')) >= Btoi(Txn.application_args[1]),
            App.globalGet(Bytes('ALGOS_BALANCE')) > algos_calc,
            App.globalGet(Bytes('TOKENS_BALANCE')) > token_calc,
        )),
        App.localPut(Int(0), Bytes('ALGOS_TO_WITHDRAW'), algos_calc),
        App.localPut(Int(0), Bytes('TOKENS_TO_WITHDRAW'), token_calc),
        App.globalPut(Bytes('ALGOS_BALANCE'), App.globalGet(Bytes('ALGOS_BALANCE')) - algos_calc),
        App.globalPut(Bytes('TOKENS_BALANCE'), App.globalGet(Bytes('TOKENS_BALANCE')) - token_calc),
        App.globalPut(
            Bytes('EXCHANGE_RATE'),
            App.globalGet(Bytes('ALGOS_BALANCE')) * ratio_decimal_points / App.globalGet(Bytes('TOKENS_BALANCE'))
        ),
        Return(Int(1))
    ])

    on_swap = Seq([
        Assert(And(
            Global.group_size() == Int(2),
            Gtxn[0].type_enum() == TxnType.ApplicationCall,
        )),
        Cond(
            [
                Gtxn[1].type_enum() == TxnType.AssetTransfer,
                Seq([
                    Assert(
                        Gtxn[1].asset_receiver() == App.globalGet(Bytes('ESCROW')),
                    ),
                    App.globalPut(
                        Bytes('TOKENS_BALANCE'),
                        App.globalGet(Bytes('TOKENS_BALANCE')) + Gtxn[1].asset_amount()
                    ),
                    App.localPut(
                        Int(0),
                        Bytes('ALGOS_TO_WITHDRAW'),
                        (App.globalGet(Bytes('EXCHANGE_RATE'))
                         * (Gtxn[1].asset_amount() * Int(100) / Int(103)))
                        / ratio_decimal_points
                    ),
                    App.globalPut(
                        Bytes('ALGOS_BALANCE'),
                        App.globalGet(Bytes('ALGOS_BALANCE')) - App.localGet(Int(0), Bytes('ALGOS_TO_WITHDRAW'))
                    ),
                ])
            ],
            [
                Gtxn[1].type_enum() == TxnType.Payment,
                Seq([
                    Assert(
                        Gtxn[1].receiver() == App.globalGet(Bytes('ESCROW')),
                    ),
                    App.globalPut(
                        Bytes('ALGOS_BALANCE'),
                        App.globalGet(Bytes('ALGOS_BALANCE')) + Gtxn[1].amount()
                    ),
                    App.localPut(
                        Int(0),
                        Bytes('TOKENS_TO_WITHDRAW'),
                        (Gtxn[1].amount() * Int(100) / Int(103))
                        * ratio_decimal_points / App.globalGet(Bytes('EXCHANGE_RATE'))
                    ),
                    App.globalPut(
                        Bytes('TOKENS_BALANCE'),
                        App.globalGet(Bytes('TOKENS_BALANCE')) - App.localGet(Int(0), Bytes('TOKENS_TO_WITHDRAW'))
                    ),
                ])
            ]
        ),
        App.globalPut(
            Bytes('EXCHANGE_RATE'),
            (App.globalGet(Bytes('TOKENS_BALANCE')) * ratio_decimal_points / App.globalGet(Bytes('ALGOS_BALANCE')))
        ),
        Return(Int(1))
    ])

    on_withdraw = Seq([
        Assert(
            Global.group_size() == Int(2),
        ),
        If(
            Gtxn[1].type_enum() == TxnType.AssetTransfer,
            Seq([
                Assert(And(
                    Gtxn[1].asset_amount() == App.localGet(Int(0), Bytes('TOKENS_TO_WITHDRAW')),
                    Gtxn[1].asset_sender() == App.globalGet(Bytes('ESCROW')),
                )),
                App.localPut(Int(0), Bytes('TOKENS_TO_WITHDRAW'), Int(0))
            ]),
            If(
                Gtxn[1].type_enum() == TxnType.Payment,
                Seq([
                    Assert(And(
                        Gtxn[1].amount() == App.localGet(Int(0), Bytes('ALGOS_TO_WITHDRAW')),
                        Gtxn[1].sender() == App.globalGet(Bytes('ESCROW')),
                    )),
                    App.localPut(Int(0), Bytes('ALGOS_TO_WITHDRAW'), Int(0))
                ]),
                Return(Int(0))
            )
        ),
        # Remove 1000 Algos that is taken as a fee
        App.globalPut(Bytes('ALGOS_BALANCE'), App.globalGet(Bytes('ALGOS_BALANCE')) - Int(1000)),
        App.globalPut(
            Bytes('EXCHANGE_RATE'),
            (App.globalGet(Bytes('TOKENS_BALANCE')) * ratio_decimal_points / App.globalGet(Bytes('ALGOS_BALANCE')))
        ),
        Return(Int(1))
    ])

    return Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnComplete.UpdateApplication, on_update],
        [Txn.on_completion() == OnComplete.DeleteApplication, Return(is_creator)],
        [Txn.on_completion() == OnComplete.OptIn, on_register],
        [Txn.application_args[0] == Bytes('ADD_LIQUIDITY'), on_add_liquidity],
        [Txn.application_args[0] == Bytes('REMOVE_LIQUIDITY'), on_remove_liquidity],
        [Txn.application_args[0] == Bytes('SWAP'), on_swap],
        [Txn.application_args[0] == Bytes('WITHDRAW'), on_withdraw]
    )


def clear():
    # Refuse to clear users state if he still has money to withdraw or liquidity tokens
    return And(
        App.localGet(Int(0), Bytes('TOKENS_TO_WITHDRAW')) == Int(0),
        App.localGet(Int(0), Bytes('ALGOS_TO_WITHDRAW')) == Int(0),
        App.localGet(Int(0), Bytes('USER_LIQUIDITY_TOKENS')) == Int(0),
    )


def escrow(app_id):
    on_asset_opt_in = And(
        Global.group_size() == Int(1),
        Txn.type_enum() == TxnType.AssetTransfer,
        Txn.asset_amount() == Int(0)
    )

    on_withdraw = And(
        Global.group_size() == Int(2),
        Gtxn[0].application_id() == Int(app_id),
        Gtxn[0].type_enum() == TxnType.ApplicationCall,
        Or(
            Gtxn[1].type_enum() == TxnType.AssetTransfer,
            Gtxn[1].type_enum() == TxnType.Payment,
        )
    )

    return Or(
        on_asset_opt_in,
        on_withdraw
    )


with open('state.teal', 'w') as f:
    state_teal = compileTeal(state(1000000), Mode.Application)
    f.write(state_teal)

with open('clear.teal', 'w') as f:
    clear_teal = compileTeal(clear(), Mode.Application)
    f.write(clear_teal)

with open('escrow.teal', 'w') as f:
    escrow_teal = compileTeal(escrow(123), Mode.Signature)
    f.write(escrow_teal)
