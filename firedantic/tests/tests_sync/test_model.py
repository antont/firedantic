from uuid import uuid4

import pytest
from pydantic import Field, ValidationError
from google.cloud.firestore import (
    Query,
)  # just for the ASCENDING / DESCENDING constants

import firedantic.operators as op
from firedantic import Model
from firedantic.exceptions import (
    CollectionNotDefined,
    InvalidDocumentID,
    ModelNotFoundError,
)
from firedantic.tests.tests_sync.conftest import (
    Company,
    CustomIDConflictModel,
    CustomIDModel,
    CustomIDModelExtra,
    Product,
    TodoList,
    User,
    UserStats,
    get_user_purchases,
)

TEST_PRODUCTS = [
    {"product_id": "a", "stock": 0},
    {"product_id": "b", "stock": 1},
    {"product_id": "c", "stock": 2},
    {"product_id": "d", "stock": 3},
]


def test_save_model(configure_db, create_company):
    company = create_company()

    assert company.id is not None
    assert company.owner.first_name == "John"
    assert company.owner.last_name == "Doe"


def test_delete_model(configure_db, create_company):
    company: Company = create_company(
        company_id="11223344-5", first_name="Jane", last_name="Doe"
    )

    _id = company.id

    company.delete()

    with pytest.raises(ModelNotFoundError):
        Company.get_by_id(_id)


def test_find_one(configure_db, create_company):
    with pytest.raises(ModelNotFoundError):
        Company.find_one()

    company_a: Company = create_company(company_id="1234555-1", first_name="Foo")
    company_b: Company = create_company(company_id="1231231-2", first_name="Bar")

    a: Company = Company.find_one({"company_id": company_a.company_id})
    b: Company = Company.find_one({"company_id": company_b.company_id})

    assert a.company_id == company_a.company_id
    assert b.company_id == company_b.company_id
    assert a.owner.first_name == "Foo"
    assert b.owner.first_name == "Bar"

    with pytest.raises(ModelNotFoundError):
        Company.find_one({"company_id": "Foo"})

    random_company = Company.find_one()
    assert random_company.company_id in {a.company_id, b.company_id}


def test_find(configure_db, create_company, create_product):
    ids = ["1234555-1", "1234567-8", "2131232-4", "4124432-4"]
    for company_id in ids:
        create_company(company_id=company_id)

    c = Company.find({"company_id": "4124432-4"})
    assert c[0].company_id == "4124432-4"
    assert c[0].owner.first_name == "John"

    d = Company.find({"owner.first_name": "John"})
    assert len(d) == 4

    for p in TEST_PRODUCTS:
        create_product(**p)

    assert len(Product.find({})) == 4

    products = Product.find({"stock": {op.GTE: 1}})
    assert len(products) == 3

    products = Product.find({"stock": {op.GTE: 2, op.LT: 4}})
    assert len(products) == 2

    products = Product.find({"product_id": {op.IN: ["a", "d", "g"]}})
    assert len(products) == 2

    with pytest.raises(ValueError):
        Product.find({"product_id": {"<>": "a"}})


def test_find_not_in(configure_db, create_company):
    ids = ["1234555-1", "1234567-8", "2131232-4", "4124432-4"]
    for company_id in ids:
        create_company(company_id=company_id)

    found = Company.find(
        {
            "company_id": {
                op.NOT_IN: [
                    "1234555-1",
                    "1234567-8",
                ]
            }
        }
    )
    assert len(found) == 2
    for company in found:
        assert company.company_id in ("2131232-4", "4124432-4")


def test_find_array_contains(configure_db, create_todolist):
    list_1 = create_todolist("list_1", ["Work", "Eat", "Sleep"])
    create_todolist("list_2", ["Learn Python", "Walk the dog"])

    found = TodoList.find({"items": {op.ARRAY_CONTAINS: "Eat"}})
    assert len(found) == 1
    assert found[0].name == list_1.name


def test_find_array_contains_any(configure_db, create_todolist):
    list_1 = create_todolist("list_1", ["Work", "Eat"])
    list_2 = create_todolist("list_2", ["Relax", "Chill", "Sleep"])
    create_todolist("list_3", ["Learn Python", "Walk the dog"])

    found = TodoList.find({"items": {op.ARRAY_CONTAINS_ANY: ["Eat", "Sleep"]}})
    assert len(found) == 2
    for lst in found:
        assert lst.name in (list_1.name, list_2.name)


def test_find_limit(configure_db, create_company):
    ids = ["1234555-1", "1234567-8", "2131232-4", "4124432-4"]
    for company_id in ids:
        create_company(company_id=company_id)

    companies_all = Company.find({})
    assert len(companies_all) == 4

    limit = 2
    companies_2 = Company.find({}, limit=limit)
    assert len(companies_2) == limit


def test_find_orderby(configure_db, create_company):
    ids_and_lastnames = (
        ("1234555-1", "A"),
        ("1234567-8", "B"),
        ("2131232-4", "C"),
        ("4124432-4", "D"),
    )
    for company_id, lastname in ids_and_lastnames:
        create_company(company_id=company_id, last_name=lastname)
    companies_ascending = Company.find(order_by=("owner.last_name", Query.ASCENDING))
    for i, company in enumerate(companies_ascending):
        assert company.owner.last_name == ids_and_lastnames[i][1]

    companies_descending = Company.find(order_by=("owner.last_name", Query.DESCENDING))
    for i, company in enumerate(companies_descending):
        neg_idx = i + 1
        assert company.owner.last_name == ids_and_lastnames[-neg_idx][1]


def test_find_multiple(configure_db, create_company):
    ids_and_lastnames = (
        ("1234555-1", "A"),
        ("1234567-8", "B"),
        ("2131232-4", "C"),
        ("4124432-4", "D"),
    )
    for company_id, lastname in ids_and_lastnames:
        create_company(company_id=company_id, last_name=lastname)
    companies_ascending = Company.find(
        order_by=("owner.last_name", Query.ASCENDING), offset=2
    )
    assert companies_ascending[0].owner.last_name == "C"

    for company_id, last_name in ids_and_lastnames:
        create_company(company_id=company_id, last_name=last_name)

    to_find = ids_and_lastnames[2]
    find_id, find_lastname = to_find
    c = Company.find({"company_id": find_id, "owner.last_name": find_lastname})
    company = c[0]
    assert company.company_id == find_id
    assert company.owner.last_name == find_lastname


def test_get_by_id(configure_db, create_company):
    c: Company = create_company(company_id="1234567-8")

    assert c.id is not None
    assert c.company_id == "1234567-8"
    assert c.owner.last_name == "Doe"

    c_2 = Company.get_by_id(c.id)

    assert c_2.id == c.id
    assert c_2.company_id == "1234567-8"
    assert c_2.owner.first_name == "John"


def test_get_by_empty_str_id(configure_db):
    with pytest.raises(ModelNotFoundError):
        Company.get_by_id("")


def test_missing_collection(configure_db):
    class User(Model):
        name: str

    with pytest.raises(CollectionNotDefined):
        User(name="John").save()


def test_model_aliases(configure_db):
    class User(Model):
        __collection__ = "User"

        first_name: str = Field(..., alias="firstName")
        city: str

    user = User(firstName="John", city="Helsinki")
    user.save()

    user_from_db = User.get_by_id(user.id)
    assert user_from_db.first_name == "John"
    assert user_from_db.city == "Helsinki"


@pytest.mark.parametrize(
    "model_id",
    [
        "abc",
        pytest.param("a" * 1500, id="1500 chars"),
        "...",
        ".foo",
        "..bar",
        "f..oo",
        "bar..",
        "__",
        "___",
        "_foo_",
        "__bar_",
        "_baz__",
        "b__a__r",
        "å",
        "😀",
        " ",
        '"',
        "'",
        "\\",
        "\x00",
        "\x01",
        "\x07",
        "!:&+-*'()",
    ],
)
def test_models_with_valid_custom_id(configure_db, model_id):
    product_id = str(uuid4())

    product = Product(product_id=product_id, price=123.45, stock=2)
    product.id = model_id
    product.save()

    found = Product.get_by_id(model_id)
    assert found.product_id == product_id

    found.delete()


@pytest.mark.parametrize(
    "model_id",
    [
        "",
        pytest.param("a" * 1501, id="1501 chars"),
        ".",
        "..",
        "____",
        "__foo__",
        "__😀__",
        "/",
        "foo/bar",
        "foo/bar/baz",
    ],
)
def test_models_with_invalid_custom_id(configure_db, model_id):
    product = Product(product_id="product 123", price=123.45, stock=2)
    product.id = model_id
    with pytest.raises(InvalidDocumentID):
        product.save()

    with pytest.raises(ModelNotFoundError):
        Product.get_by_id(model_id)


def test_truncate_collection(configure_db, create_company):
    create_company(company_id="1234567-8")
    create_company(company_id="1234567-9")

    companies = Company.find({})
    assert len(companies) == 2

    Company.truncate_collection()
    new_companies = Company.find({})
    assert len(new_companies) == 0


def test_custom_id_model(configure_db):
    c = CustomIDModel(bar="bar")
    c.save()

    models = CustomIDModel.find({})
    assert len(models) == 1

    m = models[0]
    assert m.foo is not None
    assert m.bar == "bar"


def test_custom_id_conflict(configure_db):
    CustomIDConflictModel(foo="foo", bar="bar").save()

    models = CustomIDModel.find({})
    assert len(models) == 1

    m = models[0]
    assert m.foo != "foo"
    assert m.bar == "bar"


def test_model_id_persistency(configure_db):
    c = CustomIDConflictModel(foo="foo", bar="bar")
    c.save()

    c = CustomIDConflictModel.get_by_doc_id(c.id)
    c.save()

    assert len(CustomIDConflictModel.find({})) == 1


def test_bare_model_document_id_persistency(configure_db):
    c = CustomIDModel(bar="bar")
    c.save()

    c = CustomIDModel.get_by_doc_id(c.foo)
    c.save()

    assert len(CustomIDModel.find({})) == 1


def test_bare_model_get_by_empty_doc_id(configure_db):
    with pytest.raises(ModelNotFoundError):
        CustomIDModel.get_by_doc_id("")


def test_extra_fields(configure_db):
    CustomIDModelExtra(foo="foo", bar="bar", baz="baz").save()
    with pytest.raises(ValidationError):
        CustomIDModel.find({})


def test_company_stats(configure_db, create_company):
    company: Company = create_company(company_id="1234567-8")
    company_stats = company.stats()

    stats = company_stats.get_stats()
    stats.sales = 100
    stats.save()

    # Ensure the data can be still loaded
    loaded = company.stats().get_stats()
    assert loaded.sales == stats.sales

    # And that we can still save
    loaded.sales += 1
    loaded.save()

    stats = company_stats.get_stats()
    assert stats.sales == 101


def test_subcollection_model_safety(configure_db):
    """
    Ensure you shouldn't be able to use unprepared subcollection models accidentally
    """
    with pytest.raises(CollectionNotDefined):
        UserStats.find({})


def test_get_user_purchases(configure_db):
    u = User(name="Foo")
    u.save()

    us = UserStats.model_for(u)
    us(id="2021", purchases=42).save()

    assert get_user_purchases(u.id) == 42
